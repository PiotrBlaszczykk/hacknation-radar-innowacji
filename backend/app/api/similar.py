import click
from flask import Blueprint, abort, jsonify
from sqlalchemy import select

from ..extensions import db
from ..models import Event, Innovation
from ..services import llm, novelty
from .common import json_body, page_args

bp = Blueprint("similar", __name__)


def _check(text: str, *, exclude_id: int | None = None, limit: int = 5) -> dict:
    try:
        return novelty.check_novelty(text, exclude_id=exclude_id, limit=limit)
    except llm.LLMUnavailable:
        abort(503, "Porównywanie opisów jest chwilowo niedostępne. Spróbuj ponownie za chwilę.")


@bp.post("/novelty")
def check_idea():
    text = json_body().get("text")
    if not isinstance(text, str) or len(text.strip()) < novelty.MIN_TEXT_LENGTH:
        abort(400, "Opisz pomysł w co najmniej 40 znakach.")
    return jsonify(_check(text.strip()))


def _restore(cache: dict, limit: int) -> dict:
    rows = cache["nearest"]
    cards = {
        card.id: card.to_dict() for card in db.session.scalars(
            select(Innovation).where(Innovation.id.in_([row["innovation_id"] for row in rows]))
        )
    } if rows else {}
    nearest = [
        {**{key: value for key, value in row.items() if key != "innovation_id"},
         "innovation": cards[row["innovation_id"]]}
        for row in rows if row["innovation_id"] in cards
    ]
    return {**cache["result"], "nearest": nearest[:limit]}


def _innovation_result(innovation_id: int, limit: int, *, refresh: bool = False) -> dict:
    source = db.get_or_404(Innovation, innovation_id)
    signature = novelty.card_signature(source)
    cache = (source.raw or {}).get("similar") or {}
    if not refresh and source.novelty is not None and cache.get("signature") == signature:
        return _restore(cache, limit)

    result = _check(novelty.card_text(source), exclude_id=innovation_id, limit=novelty.CANDIDATE_LIMIT)
    # Blokujemy wiersz dopiero na czas zapisu, aby zachować inne dane z radaru i skanu.
    source = db.session.get(Innovation, innovation_id, populate_existing=True, with_for_update=True)
    if source is None:
        abort(404)
    if novelty.card_signature(source) != signature:
        abort(409, "Karta zmieniła się w trakcie porównywania. Spróbuj ponownie.")

    cache = (source.raw or {}).get("similar") or {}
    if not refresh and source.novelty is not None and cache.get("signature") == signature:
        return _restore(cache, limit)

    nearest = [
        {**{key: value for key, value in item.items() if key != "innovation"},
         "innovation_id": item["innovation"]["id"]}
        for item in result["nearest"]
    ]
    source.raw = {**(source.raw or {}), "similar": {
        "signature": signature,
        "result": {key: value for key, value in result.items() if key != "nearest"},
        "nearest": nearest,
    }}
    if source.novelty != result["novelty"]:
        source.events.append(Event(
            type="novelty",
            message=f"Świeżość w radarze wynosi {result['novelty']}/100.",
            payload={"novelty": result["novelty"], "engine": result["engine"], "compared": result["compared"]},
        ))
    source.novelty = result["novelty"]
    db.session.commit()
    return {**result, "nearest": result["nearest"][:limit]}


@bp.post("/innovations/<int:innovation_id>/novelty")
def refresh_novelty(innovation_id: int):
    return jsonify(_innovation_result(innovation_id, 5, refresh=True))


@bp.get("/innovations/<int:innovation_id>/similar")
def get_similar(innovation_id: int):
    limit, _ = page_args(default_limit=5, max_limit=novelty.CANDIDATE_LIMIT)
    return jsonify(_innovation_result(innovation_id, limit))


@bp.get("/duplicates")
def get_duplicates():
    limit, _ = page_args(default_limit=20)
    return jsonify(novelty.list_duplicates(limit))


@bp.cli.command("scan")
def scan():
    """Zapisuje porównania dla panelu brokera. Wznawia od zapisanych kart."""
    try:
        novelty.scan_duplicates(click.echo)
    except llm.LLMUnavailable as exc:
        raise click.ClickException("Model decyzyjny niedostępny. Zapisane porównania zostaną użyte po wznowieniu.") from exc
