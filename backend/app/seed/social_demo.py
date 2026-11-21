from sqlalchemy import select, text

from ..extensions import db
from ..models import Innovation, Interaction, User, follow

NAME = "Lena Wrona · demo"


def install():
    for table in (follow.people, follow.organizations):
        table.create(db.engine, checkfirst=True)
    db.session.execute(text("SELECT pg_advisory_xact_lock(87190342)"))
    existing = db.session.scalar(select(User).where(User.name == NAME))
    if existing:
        return existing.id
    def person(name):
        return db.session.execute(select(User).where(User.name == name)).scalar_one()
    teacher = person("Anna Kowalczyk")
    scientist = person("dr Marek Wiśniewski")
    engineer = person("Jakub Mazur")
    investor = person("Ewa Lis")
    reader = User(name=NAME, role="poszukujacy", title="Obserwatorka innowacji · konto demonstracyjne",
                  about="Szukam pomysłów na wspólne pilotaże szkół i firm.", interests=["edukacja", "przemysl"],
                  organization_id=teacher.organization_id)
    db.session.add(reader)
    db.session.flush()
    for table, ids in ((follow.people, [teacher.id, scientist.id]),
                       (follow.organizations, [engineer.organization_id, investor.organization_id])):
        db.session.execute(table.insert(), [dict(follower_id=reader.id, target_id=i) for i in ids])
    examples = [
        ("Szkolna pracownia druku 3D dla domu pomocy społecznej", teacher, engineer,
         "Od jakiego projektu najlepiej zacząć z klasą, która pierwszy raz używa drukarki?"),
        ("Tani czujnik pyłów zawieszonych z autokalibracją", scientist, investor,
         "Jak zestawiacie pomiary czujnika z odczytami stacji referencyjnej po deszczu?"),
        ("Tutoring rówieśniczy z matematyki", teacher, scientist,
         "Chętnie zobaczę, jak dobierane są pary na pierwsze zajęcia."),
    ]
    for title, sender, responder, comment in examples:
        card = db.session.execute(select(Innovation).where(Innovation.title == title)
                                  .order_by(Innovation.id).limit(1)).scalar_one()
        for actor, kind, body in ((sender, "podbicie", None), (responder, "serce", None),
                                  (responder, "komentarz", "Demo · " + comment)):
            found = db.session.scalar(select(Interaction.id).where(
                Interaction.user_id == actor.id, Interaction.innovation_id == card.id,
                Interaction.type == kind, Interaction.body == body).limit(1))
            if found is None:
                db.session.add(Interaction(user_id=actor.id, innovation_id=card.id, type=kind, body=body))
    db.session.commit()
    return reader.id
