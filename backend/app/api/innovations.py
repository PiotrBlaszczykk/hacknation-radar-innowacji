from flask import Blueprint, abort, jsonify, request
from sqlalchemy import func, or_, select

from .. import domain
from ..extensions import db
from ..models import Event, Innovation, User
from ..services import embeddings
from .common import current_user, json_body, page_args, require_key

bp = Blueprint("innovations", __name__)

EDITABLE = (
    "title", "summary", "description", "problem", "solution", "results",
    "kind", "stage", "domains", "support_needs", "keywords",
)  # fmt: skip


def can_read_contacts(user: User | None, innovation: Innovation) -> bool:
    return user is not None and (
        user.role == "broker"
        or (user.organization_id is not None and user.organization_id == innovation.organization_id)
    )


def innovation_detail(innovation: Innovation, user: User | None):
    data = innovation.to_dict(full=True)
    if not can_read_contacts(user, innovation):
        data["events"] = [event for event in data["events"] if event["type"] != "kontakt"]
    response = jsonify(data)
    response.cache_control.no_store = True
    return response


def _validate(data: dict) -> None:
    require_key(data.get("kind"), domain.INNOVATION_KINDS, "kind")
    require_key(data.get("stage"), domain.STAGES, "stage")
    for field, allowed in (("domains", domain.DOMAINS), ("support_needs", domain.SUPPORT_NEEDS)):
        values = data.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            abort(400, f"Pole {field} musi być listą")
        for value in values:
            require_key(value, allowed, field)


@bp.get("/innovations")
def list_innovations():
    limit, offset = page_args()
    query = select(Innovation)

    for field in ("kind", "stage", "status", "origin"):
        if value := request.args.get(field):
            query = query.where(getattr(Innovation, field) == value)
    if org_id := request.args.get("organization_id", type=int):
        query = query.where(Innovation.organization_id == org_id)
    if dom := request.args.get("domain"):
        query = query.where(Innovation.domains.contains([dom]))
    if q := request.args.get("q", "").strip():
        like = f"%{q}%"
        query = query.where(
            or_(Innovation.title.ilike(like), Innovation.summary.ilike(like), Innovation.description.ilike(like))
        )

    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    if request.args.get("sort") == "score":
        order = (Innovation.score.desc().nulls_last(), Innovation.id.desc())
    else:
        order = (Innovation.created_at.desc(), Innovation.id.desc())
    rows = db.session.scalars(query.order_by(*order).limit(limit).offset(offset))
    return jsonify(items=[i.to_dict() for i in rows], total=total, limit=limit, offset=offset)


@bp.get("/innovations/<int:innovation_id>")
def get_innovation(innovation_id: int):
    innovation = db.get_or_404(Innovation, innovation_id)
    return innovation_detail(innovation, current_user())


@bp.post("/innovations")
def create_innovation():
    data = json_body()
    if not (data.get("title") or "").strip():
        abort(400, "Pole title jest wymagane")
    _validate(data)
    user = current_user()

    innovation = Innovation(
        **{k: data[k] for k in EDITABLE if k in data},
        origin="zgloszenie",
        status="zgloszona",
        claimed=True,
        structured_by=data.get("structured_by") or "czlowiek",
        author=user,
        organization_id=data.get("organization_id") or (user.organization_id if user else None),
    )
    innovation.events.append(Event(type="zgloszona", message="Innowacja zgłoszona przez formularz", actor=user))
    embeddings.try_embed(innovation)
    db.session.add(innovation)
    db.session.commit()
    return innovation_detail(innovation, user), 201


@bp.patch("/innovations/<int:innovation_id>")
def update_innovation(innovation_id: int):
    data = json_body()
    user = current_user()
    edits_status = "status" in data
    if edits_status and (user is None or user.role != "broker"):
        abort(403, "Tylko broker może zmienić status innowacji.")
    _validate(data)
    status = data.get("status")
    if status is not None and (not isinstance(status, str) or status not in domain.STATUSES):
        abort(400, "Wybierz poprawny status innowacji.")

    innovation = db.get_or_404(Innovation, innovation_id, with_for_update=True)

    changed = [key for key in EDITABLE if key in data and data[key] != getattr(innovation, key)]
    for key in changed:
        setattr(innovation, key, data[key])
    if changed and innovation.origin == "radar":
        raw = innovation.raw or {}
        innovation.raw = {**raw, "manual_fields": sorted(set(raw.get("manual_fields", [])) | set(changed))}

    if status is not None and status != innovation.status:
        innovation.events.append(
            Event(
                type="status",
                message=f"Status: {domain.STATUSES[innovation.status]} → {domain.STATUSES[status]}",
                payload={"from": innovation.status, "to": status},
                actor=user,
            )
        )
        innovation.status = status

    db.session.commit()
    return innovation_detail(innovation, user)
