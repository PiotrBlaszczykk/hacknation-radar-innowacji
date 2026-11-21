"""Wznawialny zapis kart radaru i wyników zależnych od aktywnego korpusu."""

import hashlib
import json
import struct
from collections import Counter, defaultdict
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from .. import matching, paths, scoring
from ..extensions import db
from ..models import Assessment, Event, Innovation, Need, Organization
from ..radar.enrichment import apply_structure
from ..services import llm, novelty, structuring
from . import review

KEY = "processing"
LOCK = 1782986313
PREPARE = ("structure", "review", "embedding")
ANALYZE = ("novelty", "assessment", "path", "matches")


class Busy(RuntimeError):
    pass


def _hash(*values) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _state(card: Innovation) -> dict:
    return (card.raw or {}).get(KEY) or {}


def _vector_hash(vector) -> str | None:
    return hashlib.sha256(struct.pack(f"<{len(vector)}f", *vector)).hexdigest() if vector is not None else None


def _old_automatic_archive_status(card: Innovation) -> str | None:
    decision = (card.raw or {}).get("radar_review") or {}
    if card.status != "archiwum" or decision.get("decision") != "odrzucona" or decision.get("version") == review.VERSION:
        return None
    event = max((event for event in card.events if event.type == "status"), key=lambda event: event.id, default=None)
    if event and event.actor_id is None and event.payload.get("to") == "archiwum" and event.payload.get("radar_review"):
        return event.payload.get("from")
    return None


def _archive_protected(card: Innovation) -> bool:
    raw = card.raw or {}
    return bool(
        card.claimed or card.author_id or card.structured_by in ("czlowiek", "dane przykładowe")
        or raw.get("evidence") or raw.get("patent") or raw.get("manual_fields")
        or (card.status not in ("wykryta", "oceniona") and not _old_automatic_archive_status(card))
        or any(event.actor_id is not None or event.type == paths.ACCEPTED for event in card.events)
    )


def _structure_signature(card: Innovation) -> str:
    raw = card.raw or {}
    return _hash(
        structuring.STRUCTURING_VERSION, card.title, card.description, card.origin, card.claimed, card.author_id,
        raw.get("evidence"), bool(raw.get("patent")), raw.get("manual_fields"),
        card.structured_by in ("czlowiek", "dane przykładowe"),
    )


def _signatures(card: Innovation, steps, corpus=None, targets=None) -> dict:
    raw = card.raw or {}
    state = _state(card)
    if steps == PREPARE:
        return {
            "structure": _structure_signature(card),
            "review": _hash(
                review.VERSION, state.get("structure"), raw.get("is_innovation"), raw.get("structuring_engine"),
                _archive_protected(card) if card.origin == "radar" else None,
            ),
            "embedding": _hash(current_app.config["EMBED_MODEL"], card.embedding_text()),
        }
    return {
        "novelty": _hash(novelty.card_signature(card), corpus, current_app.config["LLM_MODEL"], current_app.config.get("BASAL_URL")),
        "assessment": _hash(scoring.CRITERIA_VERSION, "evidence-t13", card.title, scoring._sources(card)),
        "path": _hash(
            "t13-1", card.kind, card.stage, card.support_needs, card.organization_id,
            card.title, card.summary, card.description, card.solution, card.results, state.get("assessment"),
        ),
        "matches": _hash("t13-1", targets, card.organization_id, card.domains, card.support_needs, card.stage, _vector_hash(card.embedding)),
    }


def _pending(card: Innovation, steps, corpus=None, targets=None) -> list[str]:
    if card.status == "archiwum":
        return ["review"] if steps == PREPARE and _old_automatic_archive_status(card) else []
    state = _state(card)
    signatures = _signatures(card, steps, corpus, targets)
    pending = [step for step in steps if (state.get(step) or {}).get("input") != signatures[step]]
    if steps == PREPARE:
        if state.get("review", {}).get("result") == "odrzucona" and "review" not in pending:
            pending.append("review")
        if card.embedding is None and "embedding" not in pending:
            pending.append("embedding")
    if steps == ANALYZE and card.novelty is None and "novelty" not in pending:
        pending.insert(0, "novelty")
    return pending


def _structure(card: Innovation) -> dict:
    raw = card.raw or {}
    previous = _state(card).get("structure")
    human_card = (
        card.origin != "radar" or card.claimed or card.author_id or raw.get("evidence") or raw.get("patent")
        or card.structured_by in ("czlowiek", "dane przykładowe")
        or card.status in ("skierowana", "w_kontakcie", "wdrazana")
    )
    if human_card:
        return {"result": "zachowana"}
    if not previous and card.structured_by and raw.get("structuring_version") == structuring.STRUCTURING_VERSION:
        return {"result": "istniejaca"}
    if not (card.description or "").strip():
        return {"result": "brak_opisu"}
    apply_structure(card, structuring.structure_text(f"{card.title}\n\n{card.description}"))
    return {"result": "zapisana"}


def _review(card: Innovation) -> dict:
    if card.origin != "radar":
        return {"result": "nie_dotyczy"}
    previous_status = _old_automatic_archive_status(card)
    result = review.evaluate(card, _archive_protected(card))
    card.raw = {**(card.raw or {}), "radar_review": result}
    if result["decision"] == "odrzucona" and card.status != "archiwum":
        db.session.add(Event(
            innovation_id=card.id, type="status", message="Radar przeniósł kartę do archiwum po przeglądzie zastosowania.",
            payload={"from": card.status, "to": "archiwum", "radar_review": result},
        ))
        card.status = "archiwum"
    elif result["decision"] != "odrzucona" and previous_status:
        db.session.add(Event(
            innovation_id=card.id, type="status", message="Radar ponownie skierował automatycznie odrzuconą kartę do przeglądu.",
            payload={"from": "archiwum", "to": previous_status, "radar_review": result},
        ))
        card.status = previous_status
    return {"result": result["decision"]}


def _embed(card: Innovation) -> dict:
    state = _state(card)
    if (
        card.embedding is not None and "embedding" not in state
        and state.get("structure", {}).get("result") != "zapisana" and not (card.raw or {}).get("manual_fields")
    ):
        return {"result": "istniejacy"}
    vectors = llm.embed([card.embedding_text()])
    if not vectors:
        raise llm.LLMUnavailable("Model nie zwrócił embeddingu karty.")
    card.embedding = vectors[0]
    return {"result": "zapisany"}


def _novelty(card: Innovation, active_ids: set[int]) -> dict:
    result = novelty.check_novelty(
        novelty.card_text(card), exclude_id=card.id, limit=novelty.CANDIDATE_LIMIT,
        where=Innovation.id.in_(active_ids), strict=True,
    )
    nearest = [
        {**{key: value for key, value in item.items() if key != "innovation"}, "innovation_id": item["innovation"]["id"]}
        for item in result["nearest"]
    ]
    card.raw = {**(card.raw or {}), "similar": {
        "signature": novelty.card_signature(card),
        "result": {key: value for key, value in result.items() if key != "nearest"},
        "nearest": nearest,
    }}
    if card.novelty != result["novelty"]:
        db.session.add(Event(
            innovation_id=card.id, type="novelty", message=f"Świeżość w radarze wynosi {result['novelty']}/100.",
            payload={key: result[key] for key in ("novelty", "engine", "compared")},
        ))
    card.novelty = result["novelty"]
    return {"result": "zapisana", "compared": result["compared"]}


def _assess(card: Innovation) -> dict:
    prior = select(Assessment).where(Assessment.innovation_id == card.id).order_by(
        Assessment.created_at.desc(), Assessment.id.desc(),
    ).limit(1)
    assessment = db.session.scalar(prior.where(
        (Assessment.assessor_id.is_not(None)) | (Assessment.engine == "czlowiek"),
    ))
    result = "zachowana"
    if assessment is None:
        state = _state(card)
        if not state.get("assessment") and state["structure"]["result"] != "zapisana" and not (card.raw or {}).get("manual_fields"):
            assessment = db.session.scalar(prior.where(Assessment.criteria_version == scoring.CRITERIA_VERSION))
        result = "istniejaca"
        if assessment is None:
            assessment = scoring.assess(card)
            result = "zapisana"
    human = assessment.assessor_id is not None or assessment.engine == "czlowiek"
    weight = scoring.scored_weight(assessment.items)
    needs_review = card.score is None or any(item.get("missing") for item in assessment.items) or (
        not human and (assessment.confidence is None or assessment.confidence < scoring.review_threshold(assessment.criteria_version))
    )
    return {"result": "zachowana" if human else result, "id": assessment.id, "weight": weight, "review": needs_review}


def _path(card: Innovation) -> dict:
    latest = paths.latest_recommendation(card.id)
    accepted = any(event.type == paths.ACCEPTED for event in card.events)
    if accepted or (latest and latest.engine == "czlowiek") or (
        card.path and card.status in ("skierowana", "w_kontakcie", "wdrazana")
    ):
        return {"result": "zachowana"}
    return {"result": "zapisana", "id": paths.recommend(card, strict=True).id}


def _matches(card: Innovation) -> dict:
    count = matching.refresh_matches(innovation_id=card.id)
    # T06 zapisuje własny znacznik wyniku w JSONB bez synchronizacji obiektu ORM.
    db.session.refresh(card, ["raw"])
    return {"result": "zapisane", "count": count}


HANDLERS = {
    "structure": _structure, "review": _review, "embedding": _embed,
    "assessment": _assess, "path": _path, "matches": _matches,
}


def _card(innovation_id, steps, report, changed, corpus=None, targets=None, active_ids=None) -> list[str]:
    completed = []
    for step in steps:
        if step == "matches":
            matching.lock_matches()
        card = db.session.get(Innovation, innovation_id, with_for_update=True, populate_existing=True)
        if card is None or step not in _pending(card, steps, corpus, targets):
            db.session.rollback()
            continue
        try:
            signature = _signatures(card, steps, corpus, targets)[step]
            result = _novelty(card, active_ids) if step == "novelty" else HANDLERS[step](card)
            state = {**_state(card), step: {"input": signature, **result}}
            if state.get("error", {}).get("step") == step:
                state.pop("error")
            card.raw = {**(card.raw or {}), KEY: state}
            db.session.commit()
            completed.append(step)
            changed[step] += 1
        except Exception as exc:
            db.session.rollback()
            card = db.session.get(Innovation, innovation_id, with_for_update=True, populate_existing=True)
            if card is not None:
                state = {**_state(card), "error": {
                    "id": innovation_id, "step": step, "reason": str(exc)[:500],
                    "model_unavailable": isinstance(exc, llm.LLMUnavailable), "at": datetime.now(UTC).isoformat(),
                }}
                card.raw = {**(card.raw or {}), KEY: state}
                db.session.commit()
            report(f"Błąd · karta {innovation_id} · {step} · {exc}")
            if isinstance(exc, llm.LLMUnavailable):
                raise
            break
    return completed


def _corpus(cards, active_ids) -> str:
    return _hash([
        (card.id, novelty.card_signature(card), _vector_hash(card.embedding))
        for card in cards if card.id in active_ids
    ])


def _targets() -> str:
    orgs = db.session.execute(
        select(Organization.id, Organization.kind, Organization.interests).order_by(Organization.id)
    ).all()
    needs = db.session.scalars(select(Need).where(Need.status == "otwarte").order_by(Need.id))
    return _hash(
        [tuple(org) for org in orgs],
        [(n.id, n.organization_id, n.title, n.domains, n.offers, _vector_hash(n.embedding)) for n in needs],
    )


def _snapshot(ids) -> list[Innovation]:
    return list(db.session.scalars(
        select(Innovation).where(Innovation.id.in_(ids)).options(selectinload(Innovation.events)).order_by(Innovation.id)
    ))


def _plan(ids, steps, corpus=None, targets=None) -> list[int]:
    planned = [card.id for card in _snapshot(ids) if _pending(card, steps, corpus, targets)]
    db.session.rollback()
    return planned


def _summary(ids, corpus=None, targets=None) -> dict:
    sources = defaultdict(Counter)
    errors = []
    for card in _snapshot(ids):
        source = sources[card.source_name or card.origin]
        source["razem"] += 1
        state = _state(card)
        pending = _pending(card, PREPARE) + (_pending(card, ANALYZE, corpus, targets) if corpus else [])
        if error := state.get("error"):
            source["bledy"] += 1
            errors.append(error)
        elif card.status == "archiwum":
            source["archiwalne"] += 1
        elif pending or not corpus:
            source["w_toku"] += 1
        elif state["assessment"]["review"] or state["review"]["result"] == "przeglad":
            source["do_przegladu"] += 1
        else:
            source["aktywne_ukonczone"] += 1
        if state.get("assessment"):
            source["zapisana_ocena"] += 1
            if card.score is not None:
                source["wynik_rankingu"] += 1
        if (state.get("matches") or {}).get("count") == 0:
            source["bez_dopasowan"] += 1
    db.session.rollback()
    return {"zrodla": {key: dict(stats) for key, stats in sorted(sources.items())}, "bledy": errors}


def _run(report, *, limit, dry_run):
    ids = list(db.session.scalars(select(Innovation.id).order_by(Innovation.id)))
    prep = _plan(ids, PREPARE)
    report(f"Zakres: {len(ids)} kart. Faza I do wykonania: {len(prep)}.")
    changed = Counter()
    corpus = targets = None
    stopped = None
    try:
        if not dry_run:
            for innovation_id in prep[:limit]:
                done = _card(innovation_id, PREPARE, report, changed)
                if done:
                    report(f"I · karta {innovation_id} · {', '.join(done)}")
        cards = _snapshot(ids)
        unready = {card.id for card in cards if _pending(card, PREPARE)}
        active_ids = {card.id for card in cards if card.status != "archiwum" and card.id not in unready}
        failed = {card.id for card in cards if _state(card).get("error", {}).get("step") in PREPARE}
        if not unready - failed:
            corpus, targets = _corpus(cards, active_ids), _targets()
        db.session.rollback()
        if corpus:
            pending = _plan(active_ids, ANALYZE, corpus, targets)
            report(f"Korpus: {len(active_ids)} aktywnych kart. Faza II do wykonania: {len(pending)}.")
            if not dry_run:
                for innovation_id in pending[:limit]:
                    done = _card(innovation_id, ANALYZE, report, changed, corpus, targets, active_ids)
                    if done:
                        report(f"II · karta {innovation_id} · {', '.join(done)}")
        else:
            report("Faza II czeka na zakończenie przygotowania korpusu.")
    except llm.LLMUnavailable as exc:
        stopped = str(exc)
    return {"kroki": dict(changed), **_summary(ids, corpus, targets), "przerwano": stopped}


def run(report, *, limit=None, dry_run=False) -> dict:
    if dry_run:
        return _run(report, limit=limit, dry_run=True)
    # Połączenie dedykowane blokadzie jest niezależne od transakcji pojedynczej karty.
    with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK}):
            raise Busy("Inne polecenie processing run już działa w tej bazie.")
        try:
            return _run(report, limit=limit, dry_run=False)
        finally:
            db.session.rollback()
            connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK})
