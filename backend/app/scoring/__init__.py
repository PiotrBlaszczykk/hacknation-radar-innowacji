import re
from math import ceil
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ..extensions import db
from ..models import Assessment, Event, Innovation, User
from ..services import decisions

CRITERIA = yaml.safe_load(Path(__file__).with_name("criteria.yaml").read_text(encoding="utf-8"))
CRITERIA_VERSION = CRITERIA["version"]
LEGACY_REVIEW_THRESHOLD = 0.35
REVIEW_THRESHOLD = 0.50
NEUTRAL_SCORE = 2.5
MIN_RANK_WEIGHT = 50
MAX_PASSAGES = 16
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])|\n[ \t]*\n\s*")
PREFERRED_FIELDS = {
    "problem": "Problem",
    "nowosc": "Rozwiązanie",
    "dowody": "Efekty",
    "przenoszalnosc": "Rozwiązanie",
    "wykonalnosc": "Rozwiązanie",
    "wplyw": "Efekty",
}
QUANTITY = re.compile(r"\d|\b(?:jeden|jedna|dwa|dwie|trzy|cztery|pięć|dziesięć|kilka|kilkadziesiąt|setki|tysiące)\b", re.I)
COMPARISON = re.compile(
    r"\b(?:względem|zamiast|niż|dotychczas\w*|w porównaniu|w odróżnieniu|w przeciwieństwie|wobec|przed i po|"
    r"grup\w* kontroln\w*|grup\w* porównawcz\w*|stan\w* referencyjn\w*|"
    r"stacj\w* referencyjn\w*|z \d[^.!?]{0,30} do \d)\b",
    re.I,
)
OBSERVED = re.compile(
    r"\b(?:przetestowano|sprawdzono|przebadano|przeprowadzono|zmierzono|zanotowano|"
    r"stwierdzono|odnotowano|wykazano|porównano|zarejestrowano|uzyskano|osiągnięto|"
    r"wdrożono|zastosowano|wdrożon\w*|skorzystał\w*|objęto|obsłużono|odwiedził\w*|"
    r"spadł\w*|wzrósł|wzrosł\w*|poprawił\w*|zmniejszył\w*|"
    r"przeszedł|przeszł\w*|wykonano|wydrukowano|wydrukowanych|"
    r"przeprowadzonych? (?:wstępnych? )?(?:testach|badaniach)|"
    r"wynik[^.!?]{0,80} (?:wyższ\w*|niższ\w*)|\d+ wypożyczeń|"
    r"oszczędności[^.!?]{0,70} w pierwszym roku)\b",
    re.I,
)
PAST_EVENT_CHECKS = {
    ("dowody", "proba"), ("dowody", "efekt"), ("dowody", "odniesienie"),
    ("wplyw", "rezultat"), ("wplyw", "trwalosc"), ("przenoszalnosc", "replikacja"),
}
QUANTITY_CHECKS = {
    ("problem", "zasieg"), ("dowody", "efekt"), ("dowody", "odniesienie"), ("wplyw", "rezultat"),
}
COMPARISON_CHECKS = {("nowosc", "roznica"), ("nowosc", "porownanie"), ("dowody", "odniesienie")}
STATUSES = {
    "confirmed": "Fragment wprost potwierdza przesłankę.",
    "denied": "Fragment wprost zaprzecza przesłance.",
    "unknown": "Brak podstaw do rozstrzygnięcia na podstawie fragmentu.",
}
EMPTY_FIELDS = {"brak", "brak danych", "nie podano", "nie dotyczy", "n/d", "-", "—"}


class CardChanged(RuntimeError):
    pass


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip().rstrip(".").lower() not in EMPTY_FIELDS)


def _sources(innovation: Innovation) -> dict[str, str]:
    fields = {"Opis": innovation.description}
    if (innovation.origin != "radar" or innovation.claimed
            or innovation.structured_by == "dane przykładowe" or not _has_text(innovation.description)):
        fields.update({
            "Problem": innovation.problem,
            "Rozwiązanie": innovation.solution,
            "Efekty": innovation.results,
            "Streszczenie": innovation.summary,
        })
    raw = innovation.raw or {}
    evidence = raw.get("evidence")
    if (
        (innovation.source_name == "strony_instytucji" or raw.get("public_project"))
        and isinstance(evidence, str) and evidence == innovation.results
    ):
        fields["Efekty"] = evidence
    return {label: value.strip() for label, value in fields.items() if _has_text(value)}


def review_threshold(version: str) -> float:
    return REVIEW_THRESHOLD if version == CRITERIA_VERSION else LEGACY_REVIEW_THRESHOLD


def _aggregate(items: list[dict]) -> tuple[float, float | None]:
    scored = [item for item in items if not item.get("missing")]
    weight = sum(item["weight"] for item in scored)
    total = sum(item["weight"] * item["score"] for item in scored) / weight if weight else NEUTRAL_SCORE
    model_items = [item for item in items if not item.get("override")]
    model_weight = sum(item["weight"] for item in model_items)
    confidence = (
        sum(item["weight"] * (item.get("confidence") or 0) for item in model_items) / model_weight
        if model_weight
        else None
    )
    return round(20 * total, 6), round(confidence, 6) if confidence is not None else None


def scored_weight(items: list[dict]) -> int:
    return sum(item["weight"] for item in items if not item.get("missing"))


def _passages(sources: dict[str, str]) -> list[str]:
    sections = [
        (source, [0, *(match.end() for match in SENTENCE_BOUNDARY.finditer(source)), len(source)])
        for source in sources.values()
    ]
    count = sum(len(bounds) - 1 for _, bounds in sections)
    stride = max(1, ceil(count / (MAX_PASSAGES + 1 - len(sections))))
    return list(dict.fromkeys(
        source[bounds[index]:bounds[min(index + stride + 1, len(bounds) - 1)]].strip()
        for source, bounds in sections
        for index in range(0, len(bounds) - 1, stride)
    ))


def _quotes(title: str, sources: dict[str, str]) -> tuple[dict[str, str], list[dict]]:
    quotes = {
        key: sources[label] for key, label in PREFERRED_FIELDS.items()
        if label in sources and len(sources[label]) <= 480
    }
    criteria = [criterion for criterion in CRITERIA["criteria"] if criterion["key"] not in quotes]
    if not criteria:
        return quotes, []
    passages = _passages(sources)
    choices = {str(index): quote for index, quote in enumerate(passages, 1)}
    answers = decisions.decide(
        f"Tytuł ocenianej karty: {title}",
        {
            c["key"]: {
                "type": "choice",
                "instructions": (
                    f'{c["question"]} Wybierz fragment zawierający najbardziej konkretną podstawę do oceny '
                    "tego projektu. Szukaj opisów zdarzeń i wyników dotyczących tego projektu. Jeżeli żaden "
                    "fragment nie wnosi informacji o kryterium, wybierz brak fragmentu."
                ),
                "criteria": {**choices, "none": "Brak fragmentu odnoszącego się do kryterium."},
            }
            for c in criteria
        },
    )
    quotes.update({key: choices[value["choice"]] for key, value in answers.items() if value["choice"] in choices})
    return quotes, list(answers.values())


def _criterion(c: dict, quote: str | None, source_title: str | None = None) -> tuple[dict, dict]:
    context = (
        f'Tytuł ocenianego projektu: {source_title}. '
        "Pomiń twierdzenia o cudzych projektach i ogólnym stanie wiedzy. "
        if source_title else ""
    )
    questions = {
        check["key"]: {
            "type": "choice",
            "instructions": (
                f'{context}Czy fragment wprost potwierdza czy wprost podważa zdanie? {check["text"]} '
                "Plan nie jest wynikiem. Gdy brak rozstrzygającej informacji, wybierz brak podstaw."
            ),
            "criteria": STATUSES,
        }
        for check in c["checks"]
    }
    answers = decisions.decide(quote, questions) if quote else {}
    checks = []
    for check in c["checks"]:
        answer = answers.get(check["key"], {})
        status = answer.get("choice", "unknown")
        identity = (c["key"], check["key"])
        if status == "confirmed" and (
            (identity in QUANTITY_CHECKS and not QUANTITY.search(quote))
            or (identity in COMPARISON_CHECKS and not COMPARISON.search(quote))
            or (identity in PAST_EVENT_CHECKS and not OBSERVED.search(quote))
        ):
            status = "unknown"
        checks.append({
            **check,
            "status": status,
            "evidence": quote if status in ("confirmed", "denied") else None,
            "probabilities": answer.get("probabilities", {}),
        })

    decided = [check for check in checks if check["status"] in ("confirmed", "denied")]
    missing = not decided
    score = sum(check["points"] for check in decided if check["status"] == "confirmed")
    confidence = min(check["probabilities"][check["status"]] for check in decided) if decided else 0
    item = {
        "key": c["key"],
        "label": c["label"],
        "weight": c["weight"],
        "score": NEUTRAL_SCORE if missing else score,
        "confidence": confidence,
        "justification": (
            "Karta wymaga uzupełnienia." if missing else
            f"Potwierdzone przesłanki dają {score} z 5 punktów."
        ),
        "evidence": quote if decided else None,
        "probabilities": {},
        "missing": missing,
        "question": c["missing_question"] if any(check["status"] == "unknown" for check in checks) else None,
        "checks": checks,
    }
    return item, next(iter(answers.values()), {})


def assess(innovation: Innovation) -> Assessment:
    """Oblicza i zapisuje ocenę w bieżącej transakcji."""
    title = innovation.title
    sources = _sources(innovation)
    quotes, models = _quotes(title, sources) if sources else ({}, [])
    items = []
    for criterion in CRITERIA["criteria"]:
        key = criterion["key"]
        quote = quotes.get(key)
        source_title = title if quote != sources.get(PREFERRED_FIELDS[key]) else None
        item, model = _criterion(criterion, quote, source_title)
        if model:
            models.append(model)
        items.append(item)

    engines = " + ".join(dict.fromkeys(model["engine"] for model in models))
    calibrated = all(model["calibrated"] for model in models) if models else None
    for item in items:
        item["calibrated"] = calibrated

    # Blokada na czas zapisu pozwala oceniać bez blokowania edycji karty podczas pracy modelu.
    locked = db.session.get(Innovation, innovation.id, populate_existing=True, with_for_update=True)
    if locked is None or locked.title != title or _sources(locked) != sources:
        raise CardChanged("Karta zmieniła się w trakcie oceny. Uruchom ocenę ponownie.")
    total, confidence = _aggregate(items)
    assessment = Assessment(
        innovation_id=locked.id,
        criteria_version=CRITERIA_VERSION,
        engine=engines[:120] or "reguły:brak treści",
        total=total,
        confidence=confidence,
        items=items,
    )
    db.session.add(assessment)
    db.session.flush()

    weight = scored_weight(items)
    has_score = weight > 0
    locked.score = total if weight >= MIN_RANK_WEIGHT else None
    payload = {"assessment_id": assessment.id, "total": total, "criteria_version": CRITERIA_VERSION}
    if has_score and locked.status in ("wykryta", "zgloszona"):
        payload.update({"from": locked.status, "to": "oceniona"})
        locked.status = "oceniona"
    db.session.add(Event(
        innovation_id=locked.id,
        type="oceniona" if has_score else "ocena_niepelna",
        message="Oceniono potencjał innowacji" if has_score else "Brak danych do oceny potencjału",
        payload=payload,
    ))
    return assessment


def override(
    innovation: Innovation, previous: Assessment, broker: User, key: str, score: float, justification: str
) -> Assessment:
    original = next(item for item in previous.items if item["key"] == key)
    corrected = {
        **original,
        "score": score,
        "confidence": None,
        "justification": justification,
        "evidence": None,
        "probabilities": {},
        "missing": False,
        "question": None,
        "override": {"user_id": broker.id, "user_name": broker.name, "at": datetime.now(UTC).isoformat()},
    }
    corrected.pop("checks", None)
    items = [corrected if item["key"] == key else item for item in previous.items]
    total, confidence = _aggregate(items)
    assessment = Assessment(
        innovation_id=innovation.id,
        criteria_version=previous.criteria_version,
        engine=previous.engine,
        total=total,
        confidence=confidence,
        items=items,
        summary=previous.summary,
        assessor_id=broker.id,
    )
    db.session.add(assessment)
    db.session.flush()

    ranked = previous.criteria_version != CRITERIA_VERSION or scored_weight(items) >= MIN_RANK_WEIGHT
    innovation.score = total if ranked else None
    db.session.add(Event(
        innovation_id=innovation.id,
        type="korekta_oceny",
        message=f"Korekta oceny potencjału: {original['label']}",
        actor_id=broker.id,
        payload={
            "assessment_id": assessment.id,
            "previous_assessment_id": previous.id,
            "key": key,
            "previous_score": original["score"],
            "score": score,
            "total": total,
        },
    ))
    return assessment
