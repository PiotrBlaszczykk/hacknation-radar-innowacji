from flask import Blueprint, abort, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import defer, joinedload

from .. import domain
from ..extensions import db
from ..matching import lock_matches, refresh_matches
from ..models import Need
from ..services import embeddings
from .common import current_user, json_body, page_args, require_key

bp = Blueprint("needs", __name__)


@bp.get("/needs")
def list_needs():
    limit, offset = page_args()
    query = select(Need)
    if area := request.args.get("domain"):
        query = query.where(Need.domains.contains([area]))
    if organization_id := request.args.get("organization_id", type=int):
        query = query.where(Need.organization_id == organization_id)
    if status := request.args.get("status"):
        query = query.where(Need.status == status)

    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(
        query.options(defer(Need.embedding), joinedload(Need.organization), joinedload(Need.author))
        .order_by(Need.created_at.desc(), Need.id.desc()).limit(limit).offset(offset)
    )
    return jsonify(items=[need.to_dict() for need in rows], total=total, limit=limit, offset=offset)


@bp.get("/needs/<int:need_id>")
def get_need(need_id: int):
    return jsonify(db.get_or_404(Need, need_id).to_dict())


@bp.post("/needs")
def create_need():
    user = current_user()
    if user is None:
        abort(401, "Wybierz personę, aby opublikować zapotrzebowanie")
    if user.organization_id is None:
        abort(403, "Zapotrzebowanie musi należeć do organizacji")

    data = json_body()
    title = data.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 400:
        abort(400, "Podaj tytuł o długości od 1 do 400 znaków")
    description = data.get("description", "")
    if not isinstance(description, str) or not description.strip():
        abort(400, "Opisz, jakiego rozwiązania szukasz")

    tags = {}
    for field, allowed in (("domains", domain.DOMAINS), ("offers", domain.SUPPORT_NEEDS)):
        values = data.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            abort(400, f"Pole {field} musi być listą kluczy słownikowych")
        for value in values:
            require_key(value, allowed, field)
        tags[field] = list(dict.fromkeys(values))

    need = Need(
        title=title.strip(), description=description.strip(), author=user,
        organization_id=user.organization_id, **tags,
    )
    embeddings.try_embed(need)
    db.session.add(need)
    db.session.flush()
    refresh_matches(need_id=need.id)
    db.session.commit()
    return jsonify(need.to_dict()), 201


@bp.patch("/needs/<int:need_id>")
def close_need(need_id: int):
    user = current_user()
    if user is None:
        abort(401, "Wybierz personę, aby zamknąć zapotrzebowanie")
    if json_body().get("status") != "zamkniete":
        abort(400, "Dozwolone jest zamknięcie zapotrzebowania")
    lock_matches()
    need = db.get_or_404(Need, need_id, with_for_update=True)
    if user.role != "broker" and user.organization_id != need.organization_id:
        abort(403, "Zapotrzebowanie może zamknąć zgłaszająca organizacja lub broker")
    if need.status == "otwarte":
        need.status = "zamkniete"
        db.session.flush()
        refresh_matches(need_id=need.id)
    db.session.commit()
    return jsonify(need.to_dict())
