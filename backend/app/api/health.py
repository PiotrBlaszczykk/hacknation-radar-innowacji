from flask import Blueprint, current_app, jsonify
from sqlalchemy import func, select

from .. import domain
from ..extensions import db
from ..models import Innovation, Need, Organization
from ..services import decisions, llm

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    counts = {
        "innovations": db.session.scalar(select(func.count(Innovation.id))),
        "organizations": db.session.scalar(select(func.count(Organization.id))),
        "needs": db.session.scalar(select(func.count(Need.id))),
    }
    broken = current_app.config.get("BROKEN_MODULES", {})
    return jsonify(status="degraded" if broken else "ok", counts=counts, models=llm.status(), decisions=decisions.engine_status(), broken_modules=broken)


@bp.get("/meta")
def meta():
    return jsonify(domain.as_meta())
