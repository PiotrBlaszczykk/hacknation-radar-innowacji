"""Decyzje o równoważności potrzeb i pokryciu warunków przez kartę."""

import re
from collections import OrderedDict
from hashlib import sha256
from threading import Lock
from time import monotonic

from flask import current_app

from ..services import decisions, llm

MAX_PAIR_CHARS = 6500
CACHE_SIZE = 4096
RETRY_SECONDS = 60
CONDITIONS_HEADER = "\n\nWarunki:\n"

EQUIVALENCE = {
    "type": "choice",
    "instructions": (
        "Czy zgłoszenia A i B opisują ten sam problem w tej samej czynności, z tym samym "
        "oczekiwanym wynikiem i zgodnymi wymaganiami? Inna instytucja lub inne słowa są dopuszczalne. "
        "Wspólny temat, lecz inna czynność, cel albo sprzeczne wymagania, oznacza różne potrzeby."
    ),
    "criteria": {
        "equivalent": "Równoważne, tę samą potrzebę można zaspokoić jednym rozwiązaniem",
        "different": "Dwie różne potrzeby",
        "unknown": "Zgłoszenia są zbyt ogólne, aby potwierdzić równoważność",
    },
}

COVERAGE = {
    "type": "choice",
    "instructions": (
        "Porównaj opisaną funkcjonalność karty z celem i czynnością w zgłoszeniu. "
        "Odrębnie wypisane warunki oceniane są osobno. Wymagania zapisane w zwykłym opisie nadal obowiązują. "
        "Za podstawę uznaj wyłącznie to, co wynika z karty. Nie domyślaj się funkcji i nie uznawaj planu prac za gotową funkcję."
    ),
    "criteria": {
        "fits": "Karta opisuje działającą funkcję realizującą wskazany cel i czynność",
        "partial": "Karta realizuje konkretną część tej samej czynności, lecz części funkcji brakuje lub działa inaczej",
        "different": "Karta rozwiązuje inny problem lub inną czynność, mimo bliskiej tematyki",
        "unknown": "Opis funkcji jest zbyt ogólny lub nie wiadomo, czy działają przy wymaganiach z opisu",
    },
}

CONDITION = {
    "type": "choice",
    "criteria": {
        "supported": "Opis działania lub wyniki wprost pokazują spełnienie warunku",
        "missing": "Opis lub wyniki wprost wskazują, że warunek nie jest spełniony",
        "unverified": "Brak informacji rozstrzygającej, czy warunek jest spełniony",
    },
}


class ReviewCache:
    def __init__(self):
        self.lock = Lock()
        self.items = OrderedDict()
        self.retry_after = 0.0

    def get(self, state, questions):
        prompt_size = len(state) + sum(
            len(question["instructions"]) + sum(len(option) for option in question["criteria"].values())
            for question in questions.values()
        )
        if prompt_size > MAX_PAIR_CHARS:
            return None
        app = current_app
        key = sha256(repr((state, questions, app.config["BASAL_URL"], app.config["LLM_MODEL"])).encode()).digest()
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
            if monotonic() < self.retry_after:
                return None
            try:
                decisions_by_key = decisions.decide(state, questions, timeout=8)
                result = {
                    name: {"choice": answer["choice"], "confidence": answer.get("confidence") or 0,
                           "engine": answer["engine"], "calibrated": answer.get("calibrated", False)}
                    for name, answer in decisions_by_key.items()
                }
            except (llm.LLMUnavailable, KeyError, TypeError) as exc:
                app.logger.info("Ocena potrzeb niedostępna: %s", exc)
                self.retry_after = monotonic() + RETRY_SECONDS
                return None
            self.items[key] = result
            if len(self.items) > CACHE_SIZE:
                self.items.popitem(last=False)
            return result


def choice(answer, minimum):
    if answer and answer["confidence"] >= (minimum if answer["calibrated"] else max(minimum, 0.8)):
        return answer["choice"]
    return None


def explicit_conditions(need):
    _, marker, conditions = (need.description or "").partition(CONDITIONS_HEADER)
    return [line.strip().removeprefix("- ").strip() for line in conditions.splitlines() if line.strip()] if marker else []


def need_text(need):
    return "\n".join(filter(None, (need.title, need.description)))


def same_need(cache, a, b):
    if not (a.description or "").strip() or not (b.description or "").strip():
        return False, None, False
    if a.title == b.title and a.description == b.description:
        return True, None, True
    left, right = sorted((need_text(a), need_text(b)))
    result = cache.get(
        f"ZGŁOSZENIE A\n{left}\n\nZGŁOSZENIE B\n{right}",
        {"equivalence": EQUIVALENCE},
    )
    answer = (result or {}).get("equivalence")
    verdict = choice(answer, 0.65)
    return verdict == "equivalent", answer, verdict in ("equivalent", "different")


def find_gap(cache, need, state):
    sentences = re.split(r"(?<=[.!?])\s+|\n", need.description)
    passages = [line.strip() for line in sentences if 12 <= len(line.strip()) <= 300][:8]
    if not passages:
        return None, {}
    question = {
        "type": "choice",
        "instructions": (
            "Który fragment zgłoszenia opisuje najważniejszą funkcję lub warunek, którego pokrycia "
            "karta nie potwierdza? Wybierz dosłowną wypowiedź. Gdy nie można wskazać fragmentu, wybierz brak."
        ),
        "criteria": {**{str(i): line for i, line in enumerate(passages)}, "none": "Nie można wskazać fragmentu"},
    }
    result = cache.get(state, {"gap": question}) or {}
    verdict = choice(result.get("gap"), 0.65)
    if verdict is None or verdict == "none":
        return None, result
    return question["criteria"].get(verdict), result


def review_card(cache, need, card):
    conditions = explicit_conditions(need)
    checks = [{"requirement": condition, "status": "unverified"} for condition in conditions]

    describes_solution = any((part or "").strip() for part in (card.solution, card.description, card.summary))
    if not (need.description or "").strip() or not describes_solution:
        return "insufficient_data", "missing_description", checks, {}

    # Karta może zawierać długi tekst źródłowy. Gdy nie mieści się w kontekście,
    # nie traktujemy odczytu fragmentu jako pełnej oceny.
    state = (
        f"ZGŁOSZENIE\n{need_text(need)}\n\nKARTA\n"
        f"Tytuł: {card.title}\nProblem: {card.problem or ''}\nRozwiązanie: {card.solution or ''}\n"
        f"Streszczenie: {card.summary or ''}\nPełny opis: {card.description or ''}\n"
        f"Wyniki: {card.results or ''}"
    )
    questions = {"coverage": COVERAGE}
    if len(conditions) > 6:
        return "insufficient_data", "incomplete_review", checks, {}
    for i, condition in enumerate(conditions):
        questions[f"condition_{i}"] = {
            **CONDITION,
            "instructions": (
                "Czy karta zawiera dowód spełnienia warunku? Sam zapis warunku w zgłoszeniu "
                f"ani zapowiedź wdrożenia nie są dowodem. Warunek: {condition}"
            ),
        }

    result = cache.get(state, questions)
    if not result:
        return "insufficient_data", "incomplete_review", checks, {}

    base_answer = result.get("coverage")
    base = choice(base_answer, 0.60)
    if base == "fits" and choice(base_answer, 0.70) is None:
        base = None
    if base == "different":
        return "no_solution", "different_problem", checks, result
    if base not in ("fits", "partial"):
        return "insufficient_data", "unconfirmed_coverage", checks, result

    for i, check in enumerate(checks):
        status = choice(result.get(f"condition_{i}"), 0.70)
        if status in ("supported", "missing"):
            check["status"] = status
    if card.stage == "pomysl":
        return "insufficient_data", "idea_stage", checks, result
    if any(check["status"] != "supported" for check in checks):
        return "partial", "conditions", checks, result
    if base == "partial":
        if not checks:
            gap, gap_review = find_gap(cache, need, state)
            result = {**result, **gap_review}
            if gap:
                checks.append({"requirement": gap, "status": "unverified"})
        return "partial", "partial_functionality", checks, result
    return "fits", "described_coverage", checks, result
