from sqlalchemy import func, select

from ..extensions import db
from ..models import Event, Innovation, Need, Organization, User
from .data import INNOVATIONS, NEEDS, ORGANIZATIONS, USERS


def load_seed() -> str:
    if db.session.scalar(select(func.count(Organization.id))):
        return "Dane startowe już są w bazie, pomijam."

    orgs = {}
    for row in ORGANIZATIONS:
        row = dict(row)
        ref = row.pop("ref")
        orgs[ref] = Organization(**row)
        db.session.add(orgs[ref])

    users = {}
    for row in USERS:
        row = dict(row)
        ref = row.pop("ref")
        users[ref] = User(organization=orgs[row.pop("org")], **row)
        db.session.add(users[ref])

    for row in INNOVATIONS:
        row = dict(row)
        author = users.get(row.pop("author", None))
        org = orgs[row.pop("org")]
        innovation = Innovation(organization=org, author=author, **row)
        if innovation.origin == "radar":
            innovation.events.append(Event(type="wykryta", message=f"Wykryta w źródle: {innovation.source_name}"))
        else:
            innovation.events.append(Event(type="zgloszona", message="Innowacja zgłoszona przez formularz", actor=author))
        db.session.add(innovation)

    for row in NEEDS:
        row = dict(row)
        author = users[row.pop("author")]
        org = orgs[row.pop("org")]
        db.session.add(Need(organization=org, author=author, **row))

    db.session.commit()
    return (
        f"Załadowano: {len(ORGANIZATIONS)} organizacji, {len(USERS)} użytkowników, "
        f"{len(INNOVATIONS)} innowacji, {len(NEEDS)} zapotrzebowań."
    )
