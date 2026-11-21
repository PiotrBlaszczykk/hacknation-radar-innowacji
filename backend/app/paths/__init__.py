import re

from sqlalchemy import func, select

from .. import domain
from ..extensions import db
from ..models import Assessment, Event, Innovation, Recommendation, User
from ..services import decisions
from ..services.llm import LLMUnavailable
from .plans import plan_for


PATH_DESCRIPTIONS = {
    "rozwoj": "Zweryfikować pomysł lub dopracować pilotaż i zebrać dowody przed wyborem odbiorcy.",
    "transfer": "Przekazać technologię lub know-how do wykorzystania przez inny podmiot, z ustaleniem praw.",
    "komercjalizacja": "Przygotować ofertę dla klientów i zweryfikować odpłatny popyt, sprzedaż lub licencję.",
    "wdrozenie": "Pomóc niezależnej organizacji powtórzyć sprawdzoną praktykę i ocenić wynik jej pilotażu.",
}
MISSING_SIGNALS = {
    "rozwoj": "Silniej przemawiałaby za nią potrzeba dopracowania rozwiązania lub zebrania dowodów przed szukaniem odbiorcy.",
    "transfer": "Silniej przemawiałyby za nią gotowy do przekazania rezultat techniczny i potrzeba ustalenia praw lub warunków transferu.",
    "komercjalizacja": "Silniej przemawiałyby za nią dojrzałe rozwiązanie oraz sygnał popytu lub gotowości do przygotowania odpłatnej oferty.",
    "wdrozenie": "Silniej przemawiałyby za nią wyniki wdrożenia lub pilotażu i gotowość kolejnej organizacji do podjęcia próby.",
}
TIE_MARGIN = 1
PROPOSED = "rekomendacja"
ACCEPTED = "rekomendacja_zatwierdzona"


def latest_recommendation(innovation_id: int) -> Recommendation | None:
    return db.session.scalar(
        select(Recommendation).where(Recommendation.innovation_id == innovation_id)
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc()).limit(1)
    )


def recommendation_event(recommendation: Recommendation, event_type: str) -> Event | None:
    return db.session.scalar(
        select(Event).where(
            Event.innovation_id == recommendation.innovation_id,
            Event.type == event_type,
            Event.payload.contains({"recommendation_id": recommendation.id}),
        ).order_by(Event.id.desc()).limit(1)
    )


def _criteria(innovation: Innovation) -> dict[str, float]:
    assessment = db.session.scalar(
        select(Assessment).where(Assessment.innovation_id == innovation.id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc()).limit(1)
    )
    return {
        item["key"]: item["score"]
        for item in (assessment.items or [])
        if not item.get("missing") and isinstance(item.get("score"), (float, int))
    } if assessment else {}


def _rules(innovation: Innovation) -> tuple[dict[str, int], list[dict]]:
    scores = dict.fromkeys(domain.PATHS, 0)
    reasons = []

    def add(path: str, points: int, message: str) -> None:
        scores[path] += points
        reasons.append({"type": "rule", "path": path, "points": points, "message": message})

    stage = innovation.stage
    kind = innovation.kind
    mature = stage in {"wdrozona", "skalowana"}
    experimental = stage in {"prototyp", "pilotaz"}
    technology = kind == "technologiczna"
    practice = kind in {"edukacyjna", "organizacyjna", "procesowa", "spoleczna"}
    early = not (mature or experimental)
    org_kind = innovation.organization.kind if innovation.organization else None
    needs = set(innovation.support_needs or [])
    wants_partner = bool(needs & {"partner_wdrozeniowy", "pierwszy_uzytkownik"})
    results = (innovation.results or "").strip()
    criteria = _criteria(innovation)
    evidence = criteria.get("dowody")
    measured = evidence >= 4 if evidence is not None else bool(re.search(r"\d", results))
    replicable = mature or (stage == "pilotaz" and wants_partner)

    if early:
        message = ("Karta opisuje pomysł na wczesnym etapie." if stage == "pomysl"
                   else "Brakuje informacji o etapie prac.")
        add("rozwoj", 7, message)
    if experimental:
        add("rozwoj", 3, "Prototyp lub pilotaż daje podstawę do dalszych testów.")
    if not results and evidence is None:
        add("rozwoj", 2, "Karta i ocena nie zawierają udokumentowanych efektów.")
    if evidence is not None and evidence < 2:
        add("rozwoj", 3, "Ocena wskazuje słabe dowody działania.")
    if innovation.origin == "radar" and not innovation.claimed:
        add("rozwoj", 2, "Twórcy nie potwierdzili jeszcze karty wykrytej przez radar.")
    if needs & {"mentoring", "zespol"}:
        add("rozwoj", 2, "Twórcy szukają wsparcia mentorskiego lub osób do zespołu.")
    if "finansowanie" in needs and early:
        add("rozwoj", 1, "Twórcy szukają finansowania na wczesnym etapie.")

    if practice and mature:
        add("rozwoj", 1, "Lokalne wdrożenie pozwala dalej doskonalić rozwiązanie u twórców.")
        add("wdrozenie", 5, "Praktykę wdrożono lokalnie lub już rozszerzono jej zasięg.")
    if practice and stage == "pilotaz":
        add("wdrozenie", 1, "Doświadczenia z pilotażu mogą pomóc przygotować opis dla kolejnej organizacji.")
    if practice and replicable and wants_partner:
        add("wdrozenie", 3, "Twórcy szukają partnera wdrożeniowego lub pierwszego użytkownika praktyki.")
    if practice and replicable and measured:
        message = ("Ocena dowodów działania wynosi co najmniej 4 na 5." if evidence is not None
                   else "Wyniki w karcie zawierają dane liczbowe.")
        add("wdrozenie", 3, message)
    if practice and replicable and criteria.get("przenoszalnosc", 0) >= 4:
        add("wdrozenie", 2, "Ocena przenoszalności do innych organizacji wynosi co najmniej 4 na 5.")
    if practice and replicable and org_kind in {"szkola", "jst", "instytucja_publiczna", "ngo"}:
        add("wdrozenie", 1, "Instytucja może przekazać praktykę organizacji o podobnych zadaniach.")

    if technology and not early and org_kind == "uczelnia":
        add("transfer", 4, "Technologia powstała na uczelni i ma postać wykraczającą poza pomysł.")
    if technology and not early and "ochrona_ip" in needs:
        add("transfer", 4, "Twórcy zgłaszają potrzebę ochrony własności intelektualnej technologii.")
    if technology and not early and org_kind == "uczelnia" and wants_partner:
        add("transfer", 1, "Zespół uczelniany szuka podmiotu do współpracy przy technologii.")

    if technology and mature:
        add("komercjalizacja", 5, "Technologia działa już po wdrożeniu lokalnym lub jest skalowana.")
    if technology and not early and org_kind == "firma":
        add("komercjalizacja", 3, "Rozwiązanie techniczne rozwija przedsiębiorstwo.")
    if technology and not early and wants_partner and "finansowanie" in needs:
        add("komercjalizacja", 2, "Twórcy szukają finansowania i odbiorcy do walidacji oferty.")
    if technology and not early and measured:
        message = ("Ocena dowodów działania wynosi co najmniej 4 na 5." if evidence is not None
                   else "Karta opisuje wyniki liczbowe, które można pokazać potencjalnym odbiorcom.")
        add("komercjalizacja", 2, message)
    return scores, reasons


def _resolve(innovation: Innovation, options: list[str], reasons: list[dict], *, strict: bool) -> dict | None:
    if len(options) < 2:
        return None

    def excerpt(value: str | None) -> str:
        return (value or "brak danych")[:500]

    state = "\n".join([
        f"Karta: {innovation.title}",
        f"Rodzaj: {domain.INNOVATION_KINDS.get(innovation.kind, 'brak danych')}",
        f"Etap: {domain.STAGES.get(innovation.stage, 'brak danych')}",
        f"Organizacja: {domain.ORG_KINDS.get(innovation.organization.kind, 'brak danych') if innovation.organization else 'brak danych'}",
        "Potrzeby: " + ", ".join(domain.SUPPORT_NEEDS[key] for key in (innovation.support_needs or [])
                                if key in domain.SUPPORT_NEEDS),
        f"Opis rozwiązania: {excerpt(innovation.solution or innovation.summary or innovation.description)}",
        f"Efekty: {excerpt(innovation.results)}",
        "Reguły: " + " ".join(reason["message"] for reason in reasons),
    ])
    try:
        answer = decisions.decide_one(state, {
            "type": "choice",
            "instructions": "Wybierz najbliższy krok na podstawie karty i dowodów działania.",
            "criteria": {key: f"{domain.PATHS[key]}. {PATH_DESCRIPTIONS[key]}" for key in options},
        }, timeout=8)
    except LLMUnavailable:
        if strict:
            raise
        return None
    if answer.get("choice") not in options:
        return None
    return answer


def _record(
    innovation: Innovation, recommendation: Recommendation, details: dict, actor: User | None = None,
) -> Recommendation:
    recommendation.created_at = func.clock_timestamp()
    innovation.path = recommendation.path
    db.session.add(recommendation)
    db.session.flush()
    action = "Zmieniono rekomendowaną ścieżkę na" if actor else "Wskazano ścieżkę"
    db.session.add(Event(
        innovation_id=innovation.id, type=PROPOSED, actor=actor,
        message=f"{action} „{domain.PATHS[recommendation.path]}”",
        payload={**details, "recommendation_id": recommendation.id, "path": recommendation.path},
    ))
    return recommendation


def recommend(innovation: Innovation, *, strict: bool = False) -> Recommendation:
    """Zapisuje wynik i jego przyczyny w bieżącej transakcji."""
    scores, reasons = _rules(innovation)
    ranking = sorted(scores, key=scores.get, reverse=True)
    if not reasons:
        reasons.append({"type": "rule", "path": "rozwoj", "points": 0,
                        "message": "Karta potrzebuje dalszej weryfikacji przed wyborem odbiorcy."})
        candidates = []
    else:
        candidates = [key for key in ranking if scores[key] > 0 and scores[ranking[0]] - scores[key] <= TIE_MARGIN]
    decision = _resolve(innovation, candidates, reasons, strict=strict)
    confidence = None
    engine = "reguly"
    if decision:
        selected = decision["choice"]
        ranking.remove(selected)
        ranking.insert(0, selected)
        engine = decision.get("engine") or "model-decyzyjny"
        confidence = decision.get("confidence")
        reasons.append({
            "type": "model", "path": selected,
            "message": f"Przy zbliżonych wynikach reguł model wskazał ścieżkę „{domain.PATHS[selected]}”.",
            "probabilities": decision.get("probabilities", {}), "engine": engine,
            "calibrated": decision.get("calibrated", False),
        })

    path = ranking[0]
    alternatives = ranking[1:]
    if all(scores[key] == 0 for key in alternatives) and innovation.kind != "technologiczna":
        alternative = "wdrozenie" if path == "rozwoj" else "rozwoj"
    else:
        alternative = alternatives[0]
    if decision:
        why = f"Reguły dały zbliżone wyniki ({scores[alternative]} i {scores[path]} pkt), a model wskazał inną opcję."
    elif scores[path] == scores[alternative]:
        why = "Wyniki reguł są równe. O kolejności przesądził priorytet dalszej weryfikacji lub pozycji w słowniku ścieżek."
    else:
        why = f"Reguły przyznały tej ścieżce {scores[alternative]} pkt, a wybranej {scores[path]} pkt."
    strongest = sorted(
        (reason for reason in reasons if reason["type"] == "rule" and reason["path"] == path),
        key=lambda reason: reason["points"], reverse=True,
    )[:2]
    rationale = " ".join([f"Proponowana ścieżka to „{domain.PATHS[path]}”.", *(r["message"] for r in strongest)])
    steps, metrics = plan_for(innovation, path)
    recommendation = Recommendation(
        innovation_id=innovation.id, path=path, rationale=rationale,
        steps=steps, metrics=metrics, engine=engine[:120], confidence=confidence,
    )
    return _record(innovation, recommendation, {
        "reasons": reasons, "scores": scores,
        "alternative": {"path": alternative, "reason": f"{why} {MISSING_SIGNALS[alternative]}"},
    })


def choose_path(
    innovation: Innovation, original: Recommendation, path: str, broker: User,
) -> Recommendation:
    proposal = recommendation_event(original, PROPOSED)
    details = proposal.payload if proposal else {}
    steps, metrics = plan_for(innovation, path)
    path_label = domain.PATHS[path]
    original_label = domain.PATHS[original.path]
    reason = f"Broker wybrał ścieżkę „{path_label}”. Poprzednia rekomendacja wskazywała „{original_label}”."
    recommendation = Recommendation(
        innovation_id=innovation.id, path=path, rationale=reason, steps=steps, metrics=metrics, engine="czlowiek",
    )
    return _record(innovation, recommendation, {
        "reasons": [{"type": "broker", "path": path, "message": reason}, *details.get("reasons", [])],
        "scores": details.get("scores", {}),
        "alternative": {"path": original.path, "reason": "Broker wybrał inną ścieżkę przy zatwierdzeniu."},
    }, actor=broker)
