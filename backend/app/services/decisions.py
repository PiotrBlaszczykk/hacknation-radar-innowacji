"""Decyzje typowane na modelu basal: wybór z listy, tak/nie, skala, wiele etykiet.

Zamiast prosić model o tekst, zadajemy pytanie z zamkniętą listą odpowiedzi i czytamy
prawdopodobieństwo każdej opcji. Wynik jest powtarzalny, a pewność mówi, kiedy decyzję
powinien podjąć człowiek.

Dwa silniki, ten sam kształt pytań i odpowiedzi (zgodny z API basal-serve, /v1/systemone):
- basal-serve (gdy ustawiony BASAL_URL): prompt i kalibracja takie, na jakich model był uczony;
- zastępczy: jedno wywołanie Ollamy na pytanie, odpowiedź jednym znakiem, prawdopodobieństwa
  z logitów. Działa zawsze, ale prawdopodobieństwa nie są skalibrowane.

Pytania:
    {"type": "choice", "instructions": "...", "criteria": {"klucz": "opis", ...}}
    {"type": "noul",   "instructions": "..."}                                   # tak/nie
    {"type": "score",  "instructions": "...", "criteria": ["poziom 0", "poziom 1", ...]}
    {"type": "multi",  "instructions": "...", "criteria": {"klucz": "opis", ...}, "threshold": 0.5}

Odpowiedzi (każda ma też "confidence" i "engine"):
    choice: {"choice": "klucz", "probabilities": {"klucz": p, ...}}
    noul:   {"noul": p_tak, "probabilities": {"true": p, "false": p}}
    score:  {"score": poziom_oczekiwany, "probabilities": {"0": p, ...}}
    multi:  {"selected": ["klucz", ...], "probabilities": {"klucz": p, ...}}
"""

import math
import string

import httpx
from flask import current_app

from .llm import LLMUnavailable

MAX_OPTIONS = 20  # tyle prawdopodobieństw na pozycję zwraca Ollama


def decide(state: str, questions: dict[str, dict], *, timeout: float = 120) -> dict[str, dict]:
    """Odpowiada na wszystkie pytania o ten sam tekst. Rzuca LLMUnavailable, gdy żaden silnik nie działa."""
    for name, question in questions.items():
        if question.get("type") not in ("choice", "noul", "score", "multi"):
            raise ValueError(f"Pytanie {name}: nieobsługiwany typ {question.get('type')}")
        if len(question.get("criteria") or []) > MAX_OPTIONS:
            raise ValueError(f"Pytanie {name}: najwyżej {MAX_OPTIONS} opcji")

    if current_app.config.get("BASAL_URL"):
        try:
            return _basal_serve(state, questions, timeout)
        except LLMUnavailable as e:
            current_app.logger.warning("basal-serve niedostępny, używam silnika zastępczego: %s", e)
    return {name: _fallback(state, question, timeout) for name, question in questions.items()}


def decide_one(state: str, question: dict, **kwargs) -> dict:
    return decide(state, {"q": question}, **kwargs)["q"]


def engine_status() -> dict:
    url = current_app.config.get("BASAL_URL")
    if not url:
        return {"engine": "ollama-logprobs", "calibrated": False}
    try:
        httpx.get(url.rstrip("/") + "/health", timeout=2).raise_for_status()
        return {"engine": "basal-serve", "calibrated": True}
    except httpx.HTTPError:
        return {"engine": "ollama-logprobs", "calibrated": False, "note": "basal-serve nie odpowiada"}


# --- basal-serve -------------------------------------------------------------


def _basal_serve(state: str, questions: dict[str, dict], timeout: float) -> dict[str, dict]:
    url = current_app.config["BASAL_URL"].rstrip("/") + "/v1/systemone"
    try:
        response = httpx.post(url, json={"state": state, "questions": questions, "lang": "pl"}, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as e:
        raise LLMUnavailable(f"basal-serve: {e}") from e

    engine = f"basal-serve:{body.get('model', '?')}"
    answers = {}
    for name in questions:
        answer = body["answers"][name]
        answer.setdefault("confidence", answer.get("set_confidence"))  # multi zwraca pewność całego zestawu
        answer["engine"] = engine
        answer["calibrated"] = True
        answers[name] = answer
    return answers


# --- silnik zastępczy: Ollama + logity ---------------------------------------


def _letters(n: int) -> list[str]:
    return list(string.ascii_uppercase[:n])


def _ask_codes(state: str, instructions: str, options: list[tuple[str, str]], timeout: float) -> list[float]:
    """Pyta model o jedną z opcji (kod, opis) i zwraca prawdopodobieństwa w kolejności opcji."""
    listing = "\n".join(f"{code}: {text}" for code, text in options)
    codes = [code for code, _ in options]
    payload = {
        "model": current_app.config["LLM_MODEL"],
        "stream": False,
        "logprobs": True,
        "top_logprobs": MAX_OPTIONS,
        "options": {"temperature": 0, "num_ctx": current_app.config["LLM_NUM_CTX"], "num_predict": 1},
        "messages": [
            {
                "role": "system",
                "content": "Podejmujesz decyzję na podstawie podanego tekstu. "
                f"Odpowiedz jednym znakiem spośród: {', '.join(codes)}.",
            },
            {"role": "user", "content": f"{state}\n\nPytanie: {instructions}\n{listing}\n\nOdpowiedź:"},
        ],
    }
    try:
        response = httpx.post(current_app.config["OLLAMA_URL"].rstrip("/") + "/api/chat", json=payload, timeout=timeout)
        response.raise_for_status()
        top = response.json()["logprobs"][0]["top_logprobs"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMUnavailable(f"Model decyzyjny niedostępny: {e}") from e

    mass = dict.fromkeys(codes, 0.0)
    for entry in top:
        token = entry["token"].strip()
        if token in mass:
            mass[token] += math.exp(entry["logprob"])
    total = sum(mass.values())
    if total == 0:
        return [1 / len(codes)] * len(codes)
    return [mass[code] / total for code in codes]


def _fallback(state: str, question: dict, timeout: float) -> dict:
    kind = question["type"]
    instructions = question["instructions"]
    meta = {"type": kind, "engine": f"ollama-logprobs:{current_app.config['LLM_MODEL']}", "calibrated": False}

    if kind == "noul":
        p_yes, p_no = _ask_codes(state, instructions, [("T", "tak"), ("N", "nie")], timeout)
        return {**meta, "noul": p_yes, "probabilities": {"true": p_yes, "false": p_no}, "confidence": max(p_yes, p_no)}

    if kind == "score":
        levels = list(question["criteria"])
        probs = _ask_codes(state, instructions, [(str(i), text) for i, text in enumerate(levels)], timeout)
        expected = sum(i * p for i, p in enumerate(probs))
        return {
            **meta,
            "score": expected,
            "legend": {str(i): text for i, text in enumerate(levels)},
            "probabilities": {str(i): p for i, p in enumerate(probs)},
            "confidence": max(probs),
        }

    criteria = question["criteria"]
    if not isinstance(criteria, dict):
        criteria = {key: key for key in criteria}
    keys = list(criteria)

    if kind == "choice":
        probs = _ask_codes(state, instructions, list(zip(_letters(len(keys)), criteria.values())), timeout)
        best = max(range(len(keys)), key=probs.__getitem__)
        return {**meta, "choice": keys[best], "probabilities": dict(zip(keys, probs)), "confidence": probs[best]}

    # multi: każda etykieta to osobne pytanie tak/nie
    threshold = question.get("threshold", 0.5)
    probabilities = {}
    for key, text in criteria.items():
        ask = f"{instructions}\nCzy pasuje etykieta: {text}?"
        probabilities[key] = _ask_codes(state, ask, [("T", "tak"), ("N", "nie")], timeout)[0]
    ranked = sorted(keys, key=probabilities.__getitem__, reverse=True)
    selected = [key for key in ranked if probabilities[key] >= threshold]
    selected = selected[: question["max"]] if question.get("max") else selected
    if len(selected) < question.get("min", 0):
        selected = ranked[: question["min"]]
    confidence = math.prod(p if key in selected else 1 - p for key, p in probabilities.items())
    return {
        **meta,
        "selected": selected,
        "probabilities": probabilities,
        "threshold": threshold,
        "set_confidence": confidence,
        "confidence": confidence,
    }
