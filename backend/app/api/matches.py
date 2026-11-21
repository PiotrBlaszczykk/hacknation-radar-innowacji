import click
from flask import Blueprint, abort, jsonify

from .. import domain
from ..extensions import db
from ..matching import INNOVATION_CACHE_KEY, active_matches, lock_matches, refresh_matches
from ..models import Event, Innovation, Match, Need
from .common import current_user, json_body

bp = Blueprint("matches", __name__)

EARLIER_STATUSES = tuple(domain.STATUSES)[:tuple(domain.STATUSES).index("w_kontakcie")]
MUTABLE_STATUSES = domain.MATCH_STATUSES.keys() - {"proponowane"}


def _match_response(query, *, include_innovation=False):
    rows = db.session.scalars(query.order_by(Match.score.desc(), Match.id)).all()
    items = []
    for match in rows:
        item = match.to_dict()
        if include_innovation:
            item["innovation"] = match.innovation.to_dict()
        items.append(item)
    return jsonify(items=items, total=len(items))


@bp.get("/innovations/<int:innovation_id>/matches")
def innovation_matches(innovation_id: int):
    innovation = db.get_or_404(Innovation, innovation_id)
    query = active_matches().where(Match.innovation_id == innovation_id)
    if not (innovation.raw or {}).get(INNOVATION_CACHE_KEY):
        refresh_matches(innovation_id=innovation_id)
        db.session.commit()
    return _match_response(query)


@bp.post("/innovations/<int:innovation_id>/matches/refresh")
def refresh_innovation(innovation_id: int):
    db.get_or_404(Innovation, innovation_id)
    refresh_matches(innovation_id=innovation_id)
    db.session.commit()
    return _match_response(active_matches().where(Match.innovation_id == innovation_id))


@bp.get("/needs/<int:need_id>/matches")
def need_matches(need_id: int):
    need = db.get_or_404(Need, need_id)
    query = active_matches().where(Match.need_id == need_id)
    if need.status != "otwarte":
        return _match_response(
            db.select(Match).where(Match.need_id == need_id, Match.status != "proponowane"),
            include_innovation=True,
        )
    refresh_matches(need_id=need_id)
    db.session.commit()
    return _match_response(query, include_innovation=True)


@bp.patch("/matches/<int:match_id>")
def update_match(match_id: int):
    status = json_body().get("status")
    if not isinstance(status, str) or status not in MUTABLE_STATUSES:
        abort(400, "Wybierz status: zainteresowanie, kontakt albo odrzucone")
    user = current_user()
    if user is None:
        abort(401, "Wybierz personę, aby zmienić status dopasowania")

    lock_matches()
    match = db.get_or_404(Match, match_id)
    if status == "zainteresowanie":
        if user.organization_id is None or user.organization_id != match.organization_id:
            abort(403, "Zainteresowanie może zgłosić osoba z dopasowanej organizacji")
    elif user.role != "broker":
        abort(403, "Tę zmianę może wprowadzić broker innowacji")

    if status == match.status:
        return jsonify(match.to_dict())
    if (match.need and match.need.status != "otwarte") or not (match.factors or {}).get("eligible", True):
        abort(409, "To dopasowanie nie jest już dostępne")
    if status == "zainteresowanie" and match.status != "proponowane":
        abort(409, "To dopasowanie zostało już rozpatrzone")

    target = match.organization.name if match.organization else "Organizacja"
    actor_org = user.organization.name if user.organization else None
    actor_label = f"{user.name} ({actor_org})" if actor_org else user.name
    messages = {
        "zainteresowanie": f"{actor_label} zgłasza zainteresowanie innowacją.",
        "kontakt": f"{actor_label} łączy twórców z organizacją „{target}”.",
        "odrzucone": f"{actor_label} odrzuca dopasowanie do organizacji „{target}”.",
    }
    payload = {
        "match_id": match.id, "from": match.status, "to": status,
        "organization_id": match.organization_id, "organization": target,
        "actor_organization_id": user.organization_id, "actor_organization": actor_org,
    }
    if status == "kontakt":
        innovation = db.session.get(Innovation, match.innovation_id, with_for_update=True, populate_existing=True)
        if innovation.status in EARLIER_STATUSES:
            payload["innovation_status"] = {"from": innovation.status, "to": "w_kontakcie"}
            innovation.status = "w_kontakcie"

    match.status = status
    db.session.add(Event(
        innovation_id=match.innovation_id, type="dopasowanie", message=messages[status],
        actor_id=user.id, payload=payload,
    ))
    db.session.commit()
    return jsonify(match.to_dict())


@bp.cli.command("run")
def run_matches():
    count = refresh_matches()
    db.session.commit()
    click.echo(f"Zapisano lub odświeżono {count} dopasowań.")
