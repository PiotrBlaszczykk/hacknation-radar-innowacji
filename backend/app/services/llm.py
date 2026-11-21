"""Klient lokalnych modeli przez Ollamę: generowanie JSON według schematu i embeddingi.

Modele działają lokalnie, więc treść zgłoszeń nie opuszcza maszyny.
"""

import json

import httpx
from flask import current_app


class LLMUnavailable(RuntimeError):
    pass


def _url(path: str) -> str:
    return current_app.config["OLLAMA_URL"].rstrip("/") + path


def chat_json(system: str, user: str, schema: dict, *, temperature: float = 0.1, timeout: float = 120) -> dict:
    """Odpowiedź modelu wymuszona do podanego JSON Schema."""
    payload = {
        "model": current_app.config["LLM_MODEL"],
        "stream": False,
        "format": schema,
        "options": {"temperature": temperature, "num_ctx": current_app.config["LLM_NUM_CTX"]},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    try:
        response = httpx.post(_url("/api/chat"), json=payload, timeout=timeout)
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
        raise LLMUnavailable(f"Model językowy niedostępny: {e}") from e


def embed(texts: list[str], *, timeout: float = 120) -> list[list[float]]:
    if not texts:
        return []
    payload = {"model": current_app.config["EMBED_MODEL"], "input": texts}
    try:
        response = httpx.post(_url("/api/embed"), json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["embeddings"]
    except (httpx.HTTPError, KeyError) as e:
        raise LLMUnavailable(f"Model embeddingów niedostępny: {e}") from e


def status() -> dict:
    """Które modele są dostępne w Ollamie (do /api/health)."""
    wanted = {"llm": current_app.config["LLM_MODEL"], "embed": current_app.config["EMBED_MODEL"]}
    try:
        tags = httpx.get(_url("/api/tags"), timeout=2).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return {name: {"model": model, "available": False} for name, model in wanted.items()}
    names = {t["name"] for t in tags} | {t["name"].split(":")[0] for t in tags}
    return {name: {"model": model, "available": model in names} for name, model in wanted.items()}
