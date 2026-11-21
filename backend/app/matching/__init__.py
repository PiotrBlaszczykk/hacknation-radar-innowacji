"""Obliczanie i zapisywanie dopasowań."""

from math import isfinite

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import defer

from .. import domain
from ..extensions import db
from ..models import Innovation, Match, Need, Organization

WEIGHTS = {
    "need": {"similarity": 0.32, "domains": 0.33, "offers": 0.22, "stage": 0.13},
    "organization": {"similarity": 0, "domains": 0.70, "offers": 0, "stage": 0.30},
}
MIN_SCORE = 0.35
SIMILARITY_BASELINE = 0.40
SIMILARITY_CEILING = 1.0
MATCH_LOCK = 1782986306
INNOVATION_CACHE_KEY = "_radar_matches_calculated"

USER_KINDS = {"jst", "instytucja_publiczna", "szkola"}
STAGES_BY_AUDIENCE = {
    "inwestor": {"pomysl": 0.15, "prototyp": 1.0, "pilotaz": 1.0, "wdrozona": 0.55, "skalowana": 0.35},
    "uzytkownik": {"pomysl": 0.10, "prototyp": 0.45, "pilotaz": 0.75, "wdrozona": 1.0, "skalowana": 1.0},
    "partner": {"pomysl": 0.35, "prototyp": 0.80, "pilotaz": 1.0, "wdrozona": 0.85, "skalowana": 0.70},
}


def lock_matches() -> None:
    # Schemat nie ma unikalności par, więc przeliczenia i decyzje serializujemy do końca transakcji.
    db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MATCH_LOCK})


def _audience(kind: str) -> str:
    if kind == "inwestor":
        return "inwestor"
    if kind in USER_KINDS:
        return "uzytkownik"
    return "partner"


def score_match(
    innovation: Innovation, organization: Organization, need: Need | None = None,
    raw_similarity: float | None = None,
) -> tuple[float, str, str, dict]:
    scope = "need" if need is not None else "organization"
    areas = set(innovation.domains or [])
    target_areas = set((need.domains if need is not None else organization.interests) or [])
    shared_areas = sorted(areas & target_areas)
    requested_support = set(innovation.support_needs or [])
    offers = set(need.offers or []) if need is not None else set()
    shared_support = sorted(requested_support & offers)

    role = _audience(organization.kind)
    if role != "inwestor":
        if "pierwszy_uzytkownik" in offers:
            role = "uzytkownik"
        elif "finansowanie" in shared_support:
            role = "inwestor"
        elif shared_support:
            role = "partner"
    similarity = None
    if need is not None and raw_similarity is not None and isfinite(raw_similarity):
        similarity = max(0.0, min(1.0, (raw_similarity - SIMILARITY_BASELINE)
                                  / (SIMILARITY_CEILING - SIMILARITY_BASELINE)))
    factors = {
        "similarity": similarity,
        "domains": len(shared_areas) / max(1, len(target_areas if need is not None else areas)),
        "offers": len(shared_support) / max(1, len(requested_support)) if need is not None else None,
        "stage": STAGES_BY_AUDIENCE[_audience(organization.kind)].get(innovation.stage, 0.0),
        "shared_domains": shared_areas,
        "shared_offers": shared_support,
        "innovation_stage": innovation.stage,
    }
    score = sum(weight * (factors[key] or 0) for key, weight in WEIGHTS[scope].items())
    return round(score, 4), role, _reason(need, factors), factors


def _reason(need: Need | None, factors: dict) -> str:
    clauses = []
    if need is not None and (factors["similarity"] or 0) >= 0.20:
        clauses.append(f"opis innowacji odpowiada na zapotrzebowanie „{need.title.rstrip('.!?')}”")
    if areas := factors["shared_domains"]:
        labels = ", ".join(f"„{domain.DOMAINS.get(key, key)}”" for key in areas)
        clauses.append(f"strony łączy obszar {labels}" if len(areas) == 1 else f"strony łączą obszary {labels}")
    if offers := factors["shared_offers"]:
        labels = ", ".join(domain.SUPPORT_NEEDS.get(key, key).lower() for key in offers)
        clauses.append(f"oferta organizacji pokrywa potrzeby twórców ({labels})")
    if factors["stage"] >= 0.75:
        stage = domain.STAGES[factors["innovation_stage"]].lower()
        clauses.append(f"etap „{stage}” sprzyja współpracy z tą organizacją")
    if not clauses:
        return "Dostępne informacje wskazują na ograniczone dopasowanie."
    sentence = ", ".join(clauses[:-1]) + " i " + clauses[-1] if len(clauses) > 1 else clauses[0]
    return sentence[0].upper() + sentence[1:] + "."


def refresh_matches(*, innovation_id: int | None = None, need_id: int | None = None) -> int:
    """Odświeża jeden zakres albo wszystkie pary, w transakcji wywołującego."""
    lock_matches()

    innovation_query = select(Innovation).options(defer(Innovation.embedding))
    need_query = select(Need).where(Need.status == "otwarte").options(defer(Need.embedding))
    existing_query = select(Match)
    similarity_query = (
        select(Innovation.id, Need.id, 1 - Innovation.embedding.cosine_distance(Need.embedding))
        .select_from(Innovation)
        .join(Need, Innovation.organization_id.is_distinct_from(Need.organization_id))
        .where(Need.status == "otwarte", Need.embedding.is_not(None), Innovation.embedding.is_not(None))
    )
    if innovation_id is not None:
        innovation_query = innovation_query.where(Innovation.id == innovation_id)
        existing_query = existing_query.where(Match.innovation_id == innovation_id)
        similarity_query = similarity_query.where(Innovation.id == innovation_id)
    if need_id is not None:
        need_query = need_query.where(Need.id == need_id)
        similarity_query = similarity_query.where(Need.id == need_id)
        existing_query = existing_query.where(
            or_(
                Match.need_id == need_id,
                Match.need_id.is_(None) & (
                    Match.organization_id == select(Need.organization_id)
                    .where(Need.id == need_id, Need.status == "otwarte").scalar_subquery()
                ),
            )
        )

    innovations = db.session.scalars(innovation_query).all()
    needs = db.session.scalars(need_query).all()
    organizations = []
    if need_id is None:
        organizations = db.session.scalars(select(Organization).where(
            ~select(Need.id).where(Need.organization_id == Organization.id, Need.status == "otwarte").exists()
        )).all()

    similarities = {(iid, nid): value for iid, nid, value in db.session.execute(similarity_query)}
    existing = {
        (match.innovation_id, match.need_id, match.organization_id): match
        for match in db.session.scalars(existing_query)
    }
    candidates = [(need.organization, need) for need in needs]
    candidates.extend((organization, None) for organization in organizations)
    kept = 0
    for innovation in innovations:
        for organization, need in candidates:
            if organization.id == innovation.organization_id:
                continue
            nid = need.id if need is not None else None
            score, role, reason, factors = score_match(
                innovation, organization, need, similarities.get((innovation.id, nid)),
            )
            if score < MIN_SCORE:
                continue
            key = (innovation.id, nid, organization.id)
            match = existing.pop(key, None)
            if match is None:
                match = Match(innovation_id=innovation.id, need_id=nid, organization_id=organization.id)
                db.session.add(match)
            match.score = score
            match.role = role
            match.reason = reason
            match.factors = factors
            kept += 1

    for match in existing.values():
        if match.status == "proponowane":
            db.session.delete(match)
        elif (match.factors or {}).get("eligible", True):
            match.factors = {**(match.factors or {}), "eligible": False}

    if need_id is None:
        # Wynik może być pusty, a obliczenie pojedynczej potrzeby daje tylko część dopasowań karty.
        marker = func.jsonb_build_object(INNOVATION_CACHE_KEY, True, type_=JSONB)
        db.session.execute(
            update(Innovation).where(Innovation.id.in_(innovation_query.with_only_columns(Innovation.id)))
            .values(raw=Innovation.raw.concat(marker), updated_at=Innovation.updated_at)
            .execution_options(synchronize_session=False)
        )
    return kept


def active_matches():
    return select(Match).where(Match.factors["eligible"].as_boolean().is_not(False))
