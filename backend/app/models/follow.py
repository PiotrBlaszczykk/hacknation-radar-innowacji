from sqlalchemy import Column, ForeignKey, Table

from ..extensions import db


def _links(name, target):
    return Table(
        name, db.metadata,
        Column("follower_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        Column("target_id", ForeignKey(target, ondelete="CASCADE"), primary_key=True),
    )


people = _links("follow_people", "users.id")
organizations = _links("follow_organizations", "organizations.id")
