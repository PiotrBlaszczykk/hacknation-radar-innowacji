from sqlalchemy import func, or_, select
from ..extensions import db
from ..models import Interaction, User, Innovation, follow


def targets(table, user_id):
    return select(table.c.target_id).where(table.c.follower_id == user_id)


def network(user_id):
    persons = targets(follow.people, user_id)
    orgs = targets(follow.organizations, user_id)
    actors = select(User.id).where(or_(User.id.in_(persons), User.organization_id.in_(orgs)))
    recent = select(Interaction.innovation_id, func.max(Interaction.created_at).label("at")).where(
        Interaction.user_id.in_(actors), Interaction.type.in_(("podbicie", "komentarz"))
    ).group_by(Interaction.innovation_id).subquery()
    visible = or_(Innovation.author_id.in_(persons), Innovation.organization_id.in_(orgs),
                  Innovation.id.in_(select(recent.c.innovation_id)))
    return visible, recent


def decorate(items, user_id):
    if not items:
        return
    by_id = {item["id"]: item for item in items}
    persons = set(db.session.scalars(targets(follow.people, user_id)))
    orgs = set(db.session.scalars(targets(follow.organizations, user_id)))
    for item in items:
        item.update(liked=False, likes=0, comments=[], repost_by=None,
                    follows_author=(item.get("author") or {}).get("id") in persons,
                    follows_org=(item.get("organization") or {}).get("id") in orgs)
    counts = db.session.execute(select(Interaction.innovation_id, func.count(),
        func.count().filter(Interaction.user_id == user_id)).where(
        Interaction.innovation_id.in_(by_id), Interaction.type == "serce"
    ).group_by(Interaction.innovation_id))
    for card, count, mine in counts:
        by_id[card].update(likes=count, liked=bool(mine))
    ordered = select(Interaction.innovation_id.label("card"), Interaction.type, Interaction.body,
        User.name, func.row_number().over(partition_by=(Interaction.innovation_id, Interaction.type),
        order_by=(Interaction.created_at.desc(), Interaction.id.desc())).label("position")
    ).join(User, User.id == Interaction.user_id).where(
        Interaction.innovation_id.in_(by_id), Interaction.type.in_(("komentarz", "podbicie"))
    ).subquery()
    for row in db.session.execute(select(ordered).where(ordered.c.position <= 2).order_by(ordered.c.position)):
        item = by_id[row.card]
        if row.type == "komentarz":
            item["comments"].append({"name": row.name, "body": row.body})
        elif row.position == 1:
            item["repost_by"] = row.name
