"""Scenariusz T23 na oznaczonej kopii. Uruchom z backendu przez uv run python."""

import argparse
import os

from sqlalchemy import select, text

from app import create_app
from app.extensions import db
from app.models import Event, Innovation, Need, Organization, User
from app.services import llm

PREFIX = "[DEMO T23] "
TITLE = "Napisy na żywo podczas obrad rady"
FIRST_DESCRIPTION = "Chcemy umożliwić niesłyszącym mieszkańcom śledzenie transmisji sesji rady gminy dzięki napisom na żywo."
CONDITION = "Polskie napisy muszą pojawiać się w trakcie obrad, z opóźnieniem najwyżej 3 sekund."
CONDITIONS = f"\n\nWarunki:\n- {CONDITION}"
DOMAINS = ["administracja", "cyfryzacja_ict"]
ORG_NAMES = ["Gmina Widok", "Powiat Brzeźny", "Miasto Słowików"]


def seed(app):
    if db.session.scalar(select(Need.id).where(Need.title == PREFIX + TITLE)):
        print("Próbki T23 już są w kopii.")
        return

    people = [
        User(name=PREFIX + name, role="poszukujacy", organization=Organization(
            name=PREFIX + name, kind="jst", description="Fikcyjna instytucja do demonstracji T23.",
        ))
        for name in ORG_NAMES
    ]
    needs = [
        (0, TITLE, FIRST_DESCRIPTION + CONDITIONS, ["pierwszy_uzytkownik"]),
        (1, "Tekst wypowiedzi radnych w transmisji",
         "Szukamy narzędzia, które zamieni przemówienia na posiedzeniu rady powiatu na czytany tekst w obecnym przekazie wideo, aby osoby głuche mogły śledzić debatę w czasie rzeczywistym." + CONDITIONS,
         []),
        (0, TITLE, FIRST_DESCRIPTION + CONDITIONS, ["pierwszy_uzytkownik"]),
        (1, "Wyszukiwarka cytatów w zapisach sesji rady",
         "Pracownicy biura rady potrzebują przeszukiwania archiwalnych transkrypcji nagrań obrad. Wynik ma przenosić do znacznika czasu w nagraniu. Nie chodzi o transmisje na żywo.", []),
    ]
    requests = [
        Need(title=PREFIX + title, description=description, author=people[author],
             organization=people[author].organization, domains=DOMAINS, offers=offers)
        for author, title, description, offers in needs
    ]
    missing = Need(
        title=PREFIX + "Dostępność wydarzeń",
        description=None,
        author=people[2],
        organization=people[2].organization,
        domains=DOMAINS,
    )

    cards = [
        {
            "title": PREFIX + "Napisy na żywo do transmisji obrad rady",
            "problem": "Osoby niesłyszące potrzebują napisów do transmisji posiedzenia rady.",
            "solution": "Działający generator wyświetla polskie napisy na żywo do obrad w oknie transmisji. Wdrożona wersja nakłada tekst z opóźnieniem około 20 sekund.",
            "results": "Test z przesunięciem 20 sekund w zapisie transmisji.",
            "stage": "wdrozona",
        },
        {
            "title": PREFIX + "Kwerenda pełnotekstowa nagrań z posiedzeń",
            "problem": "Sekretariat szuka dawnych wypowiedzi w archiwum obrad.",
            "solution": "System indeksuje pisemne zapisy zamkniętych obrad. Wyszukanie fragmentu zwraca odsyłacz otwierający film w chwili wypowiedzi.",
            "results": "W pilotażu wyszukano 40 wypowiedzi w zakończonych posiedzeniach i sprawdzono odsyłacze do momentu nagrania.",
            "stage": "pilotaz",
        },
    ]
    author = db.session.get(User, 1)
    innovations = [
        Innovation(
            **data, domains=DOMAINS, author=author, organization=author.organization, structured_by="czlowiek",
            events=[Event(type="zgloszona", message="Próbka demonstracyjna T23", actor=author)],
        )
        for data in cards
    ]
    embedded = requests + innovations
    vectors = llm.embed([row.embedding_text() for row in embedded])
    for row, vector in zip(embedded, vectors, strict=True):
        row.embedding = vector
    db.session.add_all(people + embedded + [missing])
    db.session.commit()
    for row in requests + [missing]:
        print("Zgłoszenie", row.id, row.title)
    for row in innovations:
        print("Karta", row.id, row.title)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "serve"))
    parser.add_argument("--port", type=int, default=5035)
    args = parser.parse_args()
    app = create_app({"BASAL_URL": os.environ.get("BASAL_URL", "http://127.0.0.1:8000")})
    with app.app_context():
        marker = db.session.scalar(text(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = current_database()"
        ))
        if marker != "Wihajster T23 demo copy":
            raise SystemExit("DATABASE_URL musi wskazywać bazę oznaczoną „Wihajster T23 demo copy”.")
        if args.action == "seed":
            seed(app)
    if args.action == "serve":
        app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
