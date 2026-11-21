from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Innovation, Need, Organization, User
from .common import page_args

bp = Blueprint("organizations", __name__)


@bp.get("/organizations")
def list_organizations():
    limit, offset = page_args()
    query = select(Organization)
    if kind := request.args.get("kind"):
        query = query.where(Organization.kind == kind)
    if q := request.args.get("q", "").strip():
        query = query.where(Organization.name.ilike(f"%{q}%"))
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    innovation_count = (
        select(func.count(Innovation.id))
        .where(Innovation.organization_id == Organization.id)
        .scalar_subquery()
    )
    rows = db.session.execute(
        query.add_columns(innovation_count)
        .order_by(Organization.name, Organization.id)
        .limit(limit)
        .offset(offset)
    )
    return jsonify(
        items=[{**org.to_dict(), "innovation_count": count} for org, count in rows],
        total=total, limit=limit, offset=offset,
    )


@bp.get("/organizations/<int:organization_id>")
def get_organization(organization_id: int):
    org = db.get_or_404(Organization, organization_id)
    innovations = list(db.session.scalars(
        select(Innovation)
        .where(Innovation.organization_id == organization_id)
        .options(joinedload(Innovation.author))
        .order_by(Innovation.created_at.desc(), Innovation.id.desc())
    ))
    needs = db.session.scalars(
        select(Need)
        .where(Need.organization_id == organization_id)
        .options(joinedload(Need.author))
        .order_by(Need.created_at.desc(), Need.id.desc())
    )
    people_count = db.session.scalar(
        select(func.count(User.id)).where(User.organization_id == organization_id)
    )
    scores = [innovation.score for innovation in innovations if innovation.score is not None]
    return jsonify(
        **org.to_dict(),
        innovations=[innovation.to_dict() for innovation in innovations],
        needs=[need.to_dict() for need in needs],
        people_count=people_count,
        stats={
            "innovation_count": len(innovations),
            "assessed_count": len(scores),
            "average_score": sum(scores) / len(scores) if scores else None,
            "in_contact_or_implementing_count": sum(i.status in ("w_kontakcie", "wdrazana") for i in innovations),
        },
    )


@bp.get("/users")
def list_users():
    """Lista person do przełącznika „zaloguj jako” w prototypie."""
    rows = db.session.scalars(select(User).order_by(User.id))
    return jsonify(items=[u.to_dict() for u in rows])
