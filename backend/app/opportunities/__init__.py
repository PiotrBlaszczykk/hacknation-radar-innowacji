"""Odczyt otwartych zapotrzebowań i propozycje pokrycia, niezależnie od decyzji o dopasowaniach."""

from itertools import combinations

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Innovation, Need
from ..services import embeddings
from .review import ReviewCache, review_card, same_need

OPEN = Need.status == "otwarte"
ACTIVE = Innovation.status != "archiwum"
NEED_LIMIT = 8
NEED_THRESHOLD = 0.59
CARD_LIMIT = 3
CARD_THRESHOLD = 0.57
STATUS_ORDER = {"fits": 0, "partial": 1, "insufficient_data": 2, "no_solution": 3}


def nearest(model, need, scope, limit, threshold, *, exclude_id=None):
    return [
        (neighbor, round(similarity, 4))
        for neighbor, similarity in embeddings.nearest(
            model, need.embedding, limit=limit, where=scope, exclude_id=exclude_id,
        )
        if similarity >= threshold
    ]


def group_needs(needs, cache):
    candidates = {}
    equality = {}
    for need in needs:
        if need.embedding is None or not (need.description or "").strip():
            continue
        for other, similarity in nearest(Need, need, OPEN, NEED_LIMIT, NEED_THRESHOLD, exclude_id=need.id):
            key = tuple(sorted((need.id, other.id)))
            candidates[key] = similarity

    groups = {}
    issues = set()
    for need in needs:
        groups[need.id] = [need.id]
        if not (need.description or "").strip() or need.embedding is None:
            issues.add(need.id)
    owners = {need.id: need.id for need in needs}
    by_id = {need.id: need for need in needs}
    for (left, right), _ in sorted(candidates.items(), key=lambda item: (-item[1], item[0])):
        a, b = owners[left], owners[right]
        if a == b:
            continue
        pairs = [tuple(sorted((x, y))) for x in groups[a] for y in groups[b]]
        if any(pair not in candidates for pair in pairs):
            continue
        for x, y in pairs:
            if (x, y) not in equality:
                same, answer, assessed = same_need(cache, by_id[x], by_id[y])
                equality[(x, y)] = {"equivalent": same, "decision": answer, "similarity": candidates[(x, y)]}
                if not assessed:
                    issues.update((x, y))
        if all(equality[pair]["equivalent"] for pair in pairs):
            first, second = sorted((a, b))
            for member in groups[second]:
                owners[member] = first
            groups[first].extend(groups.pop(second))

    return [
        (sorted((by_id[i] for i in members), key=lambda need: need.id),
         [dict(need_ids=list(pair), **equality[pair]) for pair in combinations(sorted(members), 2)],
         any(i in issues for i in members))
        for members in groups.values()
    ]


def coverage(needs, cache, catalog_incomplete):
    candidates = {}
    for need in needs:
        if need.embedding is None:
            continue
        for card, similarity in nearest(Innovation, need, ACTIVE, CARD_LIMIT, CARD_THRESHOLD):
            previous = candidates.get(card.id, (card, 0))
            candidates[card.id] = (card, max(similarity, previous[1]))

    alternatives = []
    ranked = sorted(candidates.values(), key=lambda item: (-item[1], item[0].id))[:CARD_LIMIT]
    for card, similarity in ranked:
        reviews = []
        # Równoważne zgłoszenia mogą wnosić różne szczegóły, więc sprawdzamy każde źródło.
        for need in needs:
            status, reason, checks, decisions = review_card(cache, need, card)
            reviews.append({
                "need_id": need.id, "status": status, "reason": reason,
                "conditions": checks, "decisions": decisions,
            })
        statuses = {item["status"] for item in reviews}
        if statuses == {"fits"}:
            status = "fits"
        elif statuses & {"fits", "partial"}:
            status = "partial"
        elif "insufficient_data" in statuses:
            status = "insufficient_data"
        else:
            status = "no_solution"
        excerpt = next((part.strip() for part in (card.results, card.solution) if part and part.strip()), "")
        alternatives.append({
            "id": card.id, "title": card.title, "source_url": card.source_url,
            "excerpt": excerpt[:277] + "…" if len(excerpt) > 280 else excerpt,
            "similarity": similarity, "status": status, "reviews": reviews,
        })

    alternatives.sort(key=lambda item: (STATUS_ORDER[item["status"]], -item["similarity"], item["id"]))
    incomplete = catalog_incomplete or any(
        not (need.description or "").strip() or need.embedding is None for need in needs
    ) or any(
        review["status"] == "insufficient_data" for item in alternatives for review in item["reviews"]
    )
    status = alternatives[0]["status"] if alternatives else "no_solution"
    if status == "no_solution" and incomplete:
        status = "insufficient_data"
    return status, incomplete, alternatives


def analyze():
    app = current_app._get_current_object()
    cache = app.extensions.setdefault("opportunity_reviews", ReviewCache())
    needs = db.session.scalars(
        select(Need).where(OPEN).options(joinedload(Need.organization), joinedload(Need.author)).order_by(Need.id)
    ).all()
    missing_cards = db.session.scalar(
        select(func.count()).select_from(Innovation).where(ACTIVE, Innovation.embedding.is_(None))
    )
    items = []
    for group, basis, grouping_incomplete in group_needs(needs, cache):
        status, coverage_incomplete, alternatives = coverage(group, cache, bool(missing_cards))
        if status == "no_solution" and grouping_incomplete:
            status = "insufficient_data"
        representative = group[0]
        items.append({
            "id": representative.id, "title": representative.title, "description": representative.description,
            "status": status, "incomplete": grouping_incomplete or coverage_incomplete,
            "organization_count": len({need.organization_id for need in group}),
            "sources": [need.to_dict() for need in group],
            "domains": sorted({area for need in group for area in need.domains or []}),
            "grouping": basis,
            "alternatives": alternatives,
        })
    items.sort(key=lambda item: (-item["organization_count"], item["id"]))
    return {
        "items": items,
        "incomplete": any(item["incomplete"] for item in items),
        "missing_need_embeddings": sum(need.embedding is None for need in needs),
        "missing_card_embeddings": missing_cards,
        "embedding_model": app.config["EMBED_MODEL"],
    }
