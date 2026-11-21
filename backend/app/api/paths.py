from datetime import UTC

import click
from flask import Blueprint, abort, jsonify, request
from sqlalchemy import select

from .. import domain
from ..extensions import db
from ..models import Event, Innovation, Recommendation
from ..paths import ACCEPTED, PROPOSED, choose_path, latest_recommendation, recommend, recommendation_event
from ..paths.plans import instruments
from .common import current_user, json_body

bp = Blueprint("paths", __name__)


def _locked_innovation(innovation_id: int) -> Innovation:
    return db.one_or_404(select(Innovation).where(Innovation.id == innovation_id).with_for_update())


def _response(recommendation: Recommendation) -> dict:
    proposal = recommendation_event(recommendation, PROPOSED)
    accepted = recommendation_event(recommendation, ACCEPTED)
    approval = None
    if accepted:
        approval = {
            "actor_id": accepted.actor_id,
            "actor": accepted.actor.name if accepted.actor else accepted.payload.get("actor_name"),
            "created_at": accepted.created_at.replace(tzinfo=UTC).isoformat(),
        }
    details = proposal.payload if proposal else {}
    return {
        **recommendation.to_dict(), "reasons": details.get("reasons", []),
        "scores": details.get("scores", {}), "alternative": details.get("alternative"),
        "approval": approval,
    }


def _latest_or_404(innovation_id: int) -> Recommendation:
    recommendation = latest_recommendation(innovation_id)
    if recommendation is None:
        abort(404, "Brak rekomendacji dla tej innowacji")
    return recommendation


@bp.post("/innovations/<int:innovation_id>/recommend")
def generate(innovation_id: int):
    innovation = _locked_innovation(innovation_id)
    recommendation = recommend(innovation)
    result = _response(recommendation)
    db.session.commit()
    return jsonify(result)


@bp.get("/innovations/<int:innovation_id>/recommendation")
def latest(innovation_id: int):
    db.get_or_404(Innovation, innovation_id)
    return jsonify(_response(_latest_or_404(innovation_id)))


@bp.post("/innovations/<int:innovation_id>/recommendation/accept")
def accept(innovation_id: int):
    broker = current_user()
    if broker is None or broker.role != "broker":
        abort(403, "Ścieżkę może zatwierdzić broker")

    data = json_body() if request.get_data() else {}
    if "path" in data and (not isinstance(data["path"], str) or data["path"] not in domain.PATHS):
        abort(400, "Wybierz jedną z dostępnych ścieżek")

    innovation = _locked_innovation(innovation_id)
    original = _latest_or_404(innovation_id)
    path = data.get("path", original.path)
    if path == original.path and recommendation_event(original, ACCEPTED):
        return jsonify(_response(original))

    recommendation = choose_path(innovation, original, path, broker) if path != original.path else original
    previous_status = innovation.status
    innovation.path = path
    innovation.status = "skierowana"
    db.session.add(Event(
        innovation_id=innovation.id, actor=broker, type=ACCEPTED,
        message=f"Zatwierdzono ścieżkę „{domain.PATHS[path]}”",
        payload={
            "recommendation_id": recommendation.id, "path": path,
            "previous_recommendation_id": original.id, "previous_path": original.path,
            "actor_name": broker.name, "from": previous_status, "to": innovation.status,
        },
    ))
    result = _response(recommendation)
    db.session.commit()
    return jsonify(result)


@bp.get("/instruments")
def list_instruments():
    items = instruments()
    return jsonify(items=items, total=len(items))


@bp.cli.command("run")
@click.option("--missing", is_flag=True, help="Tylko innowacje bez rekomendacji.")
@click.option("--limit", default=20, type=click.IntRange(min=1), show_default=True)
def run(missing: bool, limit: int):
    """Wyznacz rekomendacje dla kart innowacji."""
    query = select(Innovation.id)
    if missing:
        query = query.where(~select(Recommendation.id).where(Recommendation.innovation_id == Innovation.id).exists())
    ids = db.session.scalars(query.order_by(Innovation.id).limit(limit)).all()
    count = 0
    for innovation_id in ids:
        innovation = _locked_innovation(innovation_id)
        if missing and latest_recommendation(innovation_id):
            db.session.rollback()
            continue
        recommendation = recommend(innovation)
        path = recommendation.path
        db.session.commit()
        count += 1
        click.echo(f"{innovation_id}  {domain.PATHS[path]}")
    click.echo(f"Zapisano rekomendacje: {count}")
