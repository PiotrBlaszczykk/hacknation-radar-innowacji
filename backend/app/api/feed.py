from flask import Blueprint, abort, jsonify, request
from sqlalchemy import delete, func, select

from .. import domain
from ..extensions import db
from ..feed import network, ranking, rules
from ..models import Innovation, Interaction
from ..services import llm
from .common import current_user, json_body, page_args, require_key

bp = Blueprint("feed", __name__)

TABS = {"dla_ciebie", "popularne", "perelki", "najnowsze", "obserwowani"}
MAX_ABOUT = 2000


def _persona():
    user = current_user()
    if user is None:
        abort(401, "Wybierz personę w nagłówku.")
    return user


@bp.get("/feed")
def get_feed():
    tab = request.args.get("tab", "dla_ciebie")
    if tab not in TABS:
        abort(400, "Nieznana zakładka feedu.")
    user = current_user()
    if tab == "dla_ciebie" and user is None:
        tab = "najnowsze"

    filters = [Innovation.status != "archiwum"]
    for name, options in (("kind", domain.INNOVATION_KINDS), ("stage", domain.STAGES), ("origin", domain.ORIGINS)):
        if value := request.args.get(name):
            require_key(value, options, name)
            filters.append(getattr(Innovation, name) == value)
    if value := request.args.get("domain"):
        require_key(value, domain.DOMAINS, "domain")
        filters.append(Innovation.domains.contains([value]))

    limit, offset = page_args(default_limit=10)
    query = request.args.get("q", "").strip() if tab == "dla_ciebie" else ""
    vector = None
    notice = None
    if query:
        if len(query) > MAX_ABOUT:
            abort(400, f"Opis może mieć najwyżej {MAX_ABOUT} znaków.")
        try:
            vector = llm.embed([query], timeout=5)[0]
        except llm.LLMUnavailable:
            notice = "Tymczasowo szukamy po słowach z opisu oraz dopasowaniu do Twojej roli i obszarów."
    elif tab == "dla_ciebie":
        vector = user.embedding

    result = ranking.feed_page(tab, filters, user, vector, query, limit, offset)
    network.decorate(result["items"], user.id if user else None)
    if tab == "perelki" and result["total"] == 0:
        result["message"] = rules.GEM_EMPTY_IN_SCOPE if len(filters) > 1 else rules.GEM_EMPTY
    if notice:
        result["notice"] = notice
    return jsonify(result)


@bp.post("/innovations/<int:innovation_id>/bump")
def toggle_bump(innovation_id: int):
    user = _persona()
    # Wspólny wiersz innowacji porządkuje równoległe przełączenia i liczenie podbić.
    exists = db.session.scalar(select(Innovation.id).where(Innovation.id == innovation_id).with_for_update())
    if exists is None:
        abort(404, "Nie znaleziono innowacji.")
    removed = db.session.execute(
        delete(Interaction).where(
            Interaction.innovation_id == innovation_id, Interaction.user_id == user.id, Interaction.type == "podbicie",
        ),
    ).rowcount
    if not removed:
        db.session.add(Interaction(innovation_id=innovation_id, user_id=user.id, type="podbicie"))
        db.session.flush()
    count = db.session.scalar(select(func.count()).select_from(Interaction).where(
        Interaction.innovation_id == innovation_id, Interaction.type == "podbicie",
    ))
    db.session.commit()
    return jsonify(bumps=count, bumped=not removed)


@bp.get("/me")
def get_me():
    return jsonify(_persona().to_dict())


@bp.patch("/me")
def update_me():
    user = _persona()
    data = json_body()
    if "interests" in data:
        interests = data["interests"]
        if not isinstance(interests, list) or any(not isinstance(key, str) or key not in domain.DOMAINS for key in interests):
            abort(400, "Wybierz obszary z dostępnej listy.")
    if "about" in data:
        about = data["about"]
        if about is not None and (not isinstance(about, str) or len(about) > MAX_ABOUT):
            abort(400, f"Opis musi być tekstem o długości do {MAX_ABOUT} znaków.")
        about = (about or "").strip() or None
        if about != user.about:
            user.about = about
            try:
                source = user.embedding_text()
                user.embedding = llm.embed([source], timeout=5)[0] if source else None
            except llm.LLMUnavailable:
                db.session.rollback()
                abort(503, "Nie udało się przeliczyć profilu. Spróbuj zapisać go ponownie za chwilę.")
    if "interests" in data:
        user.interests = list(dict.fromkeys(interests))
    db.session.commit()
    return jsonify(user.to_dict())


@bp.get("/feed/explain")
def explain_feed():
    return jsonify(sections=rules.explain())
