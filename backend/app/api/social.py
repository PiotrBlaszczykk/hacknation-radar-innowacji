from flask import Blueprint, abort, jsonify
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Event, Innovation, Interaction, User
from .common import current_user, json_body
from .innovations import can_read_contacts, innovation_detail

bp = Blueprint("social", __name__)

TOGGLES = ("obserwuje", "zainteresowany")
MESSAGE_TYPES = ("komentarz", "kontakt")
SOCIAL_TYPES = (*TOGGLES, *MESSAGE_TYPES)
MAX_MESSAGE_LENGTH = 1000
MESSAGE_SENDER = joinedload(Interaction.user).joinedload(User.organization)


def _require_user() -> User:
    user = current_user()
    if user is None:
        abort(401, "Wybierz personę")
    return user


@bp.after_request
def _disable_caching(response):
    response.cache_control.no_store = True
    return response


@bp.get("/innovations/<int:innovation_id>/interactions")
def get_interactions(innovation_id: int):
    innovation = db.get_or_404(Innovation, innovation_id)
    user = current_user()
    show_contacts = can_read_contacts(user, innovation)
    counts = dict.fromkeys(SOCIAL_TYPES, 0)
    mine = []
    rows = db.session.execute(
        select(
            Interaction.type,
            func.count(),
            func.count().filter(Interaction.user_id == (user.id if user else None)),
        )
        .where(Interaction.innovation_id == innovation_id, Interaction.type.in_(SOCIAL_TYPES))
        .group_by(Interaction.type)
        .order_by(Interaction.type)
    )
    for kind, count, own_count in rows:
        counts[kind] = count
        if own_count:
            mine.append(kind)

    messages = db.session.scalars(
        select(Interaction)
        .where(
            Interaction.innovation_id == innovation_id,
            Interaction.type.in_(MESSAGE_TYPES if show_contacts else ("komentarz",)),
        )
        .options(MESSAGE_SENDER)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc())
    )
    comments, contact_requests = [], []
    for message in messages:
        (comments if message.type == "komentarz" else contact_requests).append(message.to_dict())
    return jsonify(
        counts=counts, mine=mine, comments=comments, contact_requests=contact_requests,
        can_read_contacts=show_contacts,
    )


@bp.post("/innovations/<int:innovation_id>/interactions")
def create_interaction(innovation_id: int):
    user = _require_user()
    data = json_body()
    kind = data.get("type")
    if kind not in (*SOCIAL_TYPES, "serce"):
        abort(400, "Wybierz poprawny typ interakcji")

    body = None
    if kind in MESSAGE_TYPES:
        value = data.get("body")
        if not isinstance(value, str) or not (body := value.strip()):
            abort(400, "Wpisz treść wiadomości")
        if len(body) > MAX_MESSAGE_LENGTH:
            abort(400, f"Wiadomość może mieć do {MAX_MESSAGE_LENGTH} znaków")

    # Wspólna blokada serializuje przełączenia także wtedy, gdy wpisu jeszcze nie ma.
    innovation = db.get_or_404(Innovation, innovation_id, with_for_update=True)
    if kind in (*TOGGLES, "serce"):
        removed = db.session.scalar(
            delete(Interaction)
            .where(
                Interaction.user_id == user.id,
                Interaction.innovation_id == innovation_id,
                Interaction.type == kind,
            )
            .returning(Interaction.id)
        )
        if removed is not None:
            db.session.commit()
            return jsonify(type=kind, active=False)

    db.session.add(Interaction(innovation_id=innovation_id, user_id=user.id, type=kind, body=body))
    if kind in ("zainteresowany", "kontakt"):
        organization = user.organization.name if user.organization else None
        action = "Zgłoszono zainteresowanie" if kind == "zainteresowany" else "Poproszono o kontakt"
        db.session.add(Event(
            innovation=innovation, actor=user, type=kind,
            message=f"{action} ({organization})" if organization else action,
            payload={"organization_id": user.organization_id, "organization_name": organization},
        ))
    db.session.commit()
    return jsonify(type=kind, active=True), 201


@bp.post("/innovations/<int:innovation_id>/claim")
def claim_innovation(innovation_id: int):
    user = _require_user()
    innovation = db.get_or_404(Innovation, innovation_id, with_for_update=True)
    if innovation.claimed:
        abort(409, "Ten profil został już potwierdzony")

    organization_mismatch = user.organization_id != innovation.organization_id
    message = "Twórca potwierdził profil wykryty przez radar"
    if organization_mismatch:
        name = user.organization.name if user.organization else "bez organizacji"
        message = f"Profil potwierdziła osoba spoza organizacji innowacji ({name})"
    innovation.claimed = True
    innovation.author = user
    db.session.add(Event(
        innovation=innovation, actor=user, type="potwierdzona", message=message,
        payload={
            "organization_mismatch": organization_mismatch,
            "author_organization_id": user.organization_id,
            "innovation_organization_id": innovation.organization_id,
        },
    ))
    db.session.commit()
    return innovation_detail(innovation, user)


@bp.get("/me/activity")
def get_activity():
    user = _require_user()
    subscriptions = (
        select(Interaction.innovation_id, Interaction.type)
        .where(Interaction.user_id == user.id, Interaction.type.in_(TOGGLES))
        .distinct()
        .subquery()
    )
    rows = db.session.execute(
        select(Innovation, subscriptions.c.type)
        .join(subscriptions, subscriptions.c.innovation_id == Innovation.id)
        .options(joinedload(Innovation.organization), joinedload(Innovation.author))
        .order_by(Innovation.created_at.desc(), Innovation.id.desc())
    )
    activity = {kind: [] for kind in TOGGLES}
    for innovation, kind in rows:
        activity[kind].append(innovation.to_dict())

    contact_requests = []
    if user.organization_id is not None:
        contacts = db.session.execute(
            select(Interaction, Innovation.id, Innovation.title)
            .join(Innovation, Innovation.id == Interaction.innovation_id)
            .where(Innovation.organization_id == user.organization_id, Interaction.type == "kontakt")
            .options(MESSAGE_SENDER)
            .order_by(Interaction.created_at.desc(), Interaction.id.desc())
        )
        contact_requests = [
            {**interaction.to_dict(), "innovation": {"id": innovation_id, "title": title}}
            for interaction, innovation_id, title in contacts
        ]
    return jsonify(following=activity["obserwuje"], interested=activity["zainteresowany"], contact_requests=contact_requests)

@bp.put("/following/<kind>/<int:target_id>")
def follow_target(kind, target_id):
    from sqlalchemy.dialects.postgresql import insert
    from ..models import Organization, follow

    user = _require_user()
    if kind not in ("person", "organization"):
        abort(404)
    is_person = kind == "person"
    db.get_or_404(User if is_person else Organization, target_id)
    active = json_body().get("active")
    if type(active) is not bool or (is_person and target_id == user.id):
        abort(400, "Wybierz inny profil i stan obserwacji.")
    table = follow.people if is_person else follow.organizations
    if active:
        db.session.execute(insert(table).values(follower_id=user.id, target_id=target_id).on_conflict_do_nothing())
    else:
        db.session.execute(table.delete().where(table.c.follower_id == user.id, table.c.target_id == target_id))
    db.session.commit()
    return jsonify(active=active)
