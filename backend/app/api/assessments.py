import math

import click
from flask import Blueprint, abort, jsonify
from sqlalchemy import select

from .. import scoring
from ..extensions import db
from ..models import Assessment, Innovation
from ..services.llm import LLMUnavailable
from .common import current_user, json_body

bp = Blueprint("assessments", __name__)

MODEL_UNAVAILABLE = "Nie można teraz ocenić potencjału. Lokalny model AI jest niedostępny. Spróbuj ponownie później."


def _latest(innovation_id: int) -> Assessment | None:
    return db.session.scalar(
        select(Assessment)
        .where(Assessment.innovation_id == innovation_id)
        .order_by(Assessment.id.desc())
        .limit(1)
    )


def _serialize(assessment: Assessment) -> dict:
    data = assessment.to_dict()
    data["calibrated"] = next((item["calibrated"] for item in data["items"] if "calibrated" in item), None)
    return data


@bp.get("/criteria")
def get_criteria():
    return jsonify(scoring.CRITERIA)


@bp.post("/innovations/<int:innovation_id>/assess")
def assess_innovation(innovation_id: int):
    innovation = db.get_or_404(Innovation, innovation_id)
    try:
        assessment = scoring.assess(innovation)
    except LLMUnavailable:
        abort(503, MODEL_UNAVAILABLE)
    except scoring.CardChanged as error:
        abort(409, str(error))
    db.session.commit()
    return jsonify(_serialize(assessment))


@bp.get("/innovations/<int:innovation_id>/assessment")
def get_assessment(innovation_id: int):
    assessment = _latest(innovation_id)
    if assessment is None:
        abort(404, "Brak oceny potencjału dla tej innowacji.")
    return jsonify(_serialize(assessment))


@bp.post("/innovations/<int:innovation_id>/assessment/override")
def override_assessment(innovation_id: int):
    broker = current_user()
    if broker is None or broker.role != "broker":
        abort(403, "Tylko broker może poprawić ocenę potencjału.")

    data = json_body()
    key = data.get("key")
    score = data.get("score")
    justification = data.get("justification")
    if not isinstance(key, str) or not key:
        abort(400, "Podaj klucz kryterium.")
    if type(score) not in (int, float) or not 0 <= score <= 5 or not math.isfinite(score):
        abort(400, "Wynik musi być liczbą od 0 do 5.")
    if not isinstance(justification, str) or not justification.strip():
        abort(400, "Podaj uzasadnienie poprawki.")

    innovation = db.get_or_404(Innovation, innovation_id, with_for_update=True)
    previous = _latest(innovation_id)
    if previous is None:
        abort(404, "Brak oceny potencjału do poprawienia.")
    if not any(item["key"] == key for item in previous.items):
        abort(400, "Wybrane kryterium nie występuje w tej ocenie.")
    assessment = scoring.override(innovation, previous, broker, key, score, justification.strip())
    db.session.commit()
    return jsonify(_serialize(assessment))


@bp.cli.command("run")
@click.option("--missing", is_flag=True, help="Oceń tylko innowacje bez zapisanej oceny.")
@click.option("--limit", type=click.IntRange(min=1), default=20, show_default=True)
def run_assessments(missing: bool, limit: int):
    """Oceń innowacje i zapisuj każdą ocenę osobno."""
    query = select(Innovation.id).order_by(Innovation.id).limit(limit)
    if missing:
        query = query.where(~select(Assessment.id).where(Assessment.innovation_id == Innovation.id).exists())

    for innovation_id in db.session.scalars(query).all():
        innovation = db.session.get(Innovation, innovation_id, with_for_update=missing)
        if innovation is None or (missing and _latest(innovation_id) is not None):
            db.session.rollback()
            continue
        try:
            assessment = scoring.assess(innovation)
            total = assessment.total
            db.session.commit()
        except LLMUnavailable as error:
            db.session.rollback()
            raise click.ClickException(f"Innowacja {innovation_id}. {MODEL_UNAVAILABLE}") from error
        except scoring.CardChanged as error:
            db.session.rollback()
            click.echo(f"Innowacja {innovation_id}. {error}", err=True)
            continue
        click.echo(f"Innowacja {innovation_id} — {total:.2f}/100")
