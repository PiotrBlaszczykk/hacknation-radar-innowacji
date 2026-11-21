"""UPRP and EPO cards for the Radar source catalog and the standalone CLI."""

from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from flask import current_app
from sqlalchemy import select, text

from ...extensions import db
from ...models import Event, Innovation, Organization
from ..radon import run_lock, write_json
from .catalog import EPO, LUKASIEWICZ, SOURCES, UPRP
from .parsers import PatentError
from .transport import collect

CACHE_DIR = Path(__file__).resolve().parents[4] / "data/cache/patenty"
PUBLICATIONS = {
    "application_publication": "ogłoszenie zgłoszenia wynalazku",
    "utility_model_publication": "ogłoszenie zgłoszenia wzoru użytkowego",
    "grant_publication": "publikacja patentu i ogłoszenie o udzieleniu",
    "amended_patent_publication": "publikacja zmienionego patentu",
    "limited_patent_publication": "publikacja ograniczonego patentu",
}
RELATED_MEASUREMENT = {"PL448718A1", "PL132167U1"}


def _description(row: dict) -> str:
    patent = row["patent"]
    office = "UPRP · BUP" if patent["source_name"] == UPRP else "EPO · EPS"
    role = "Uprawnieni wg publikacji" if patent["party_role"] == "proprietor" else "Zgłaszający"
    parties = ", ".join(patent["organizations"])
    kind = PUBLICATIONS[patent["publication_type"]]
    parts = [
        row["summary"],
        f"{office} · {patent['ref']} · {kind}.",
        f"Data zgłoszenia {patent['filing_date']}. Data publikacji tego dokumentu {patent['publication_date']}.",
        f"{role} — {parties}.",
    ]
    app_publication = patent["application_publication_date"]
    if app_publication and app_publication != patent["publication_date"]:
        parts.append(f"Publikacja zgłoszenia {app_publication}.")
    if patent["grant_announced_on"]:
        notice = patent["grant_notice"]
        grant_ref = f" w WUP 11/2018 ({notice['ref']})" if notice else ""
        parts.append(f"Ogłoszenie o udzieleniu{grant_ref} {patent['grant_announced_on']}.")
    parts.append("Publikacja patentowa dokumentuje zgłoszenie lub ochronę. Wdrożenie i gotowość wymagają osobnego potwierdzenia.")
    if row["broker_note"]:
        parts.append(row["broker_note"])
    return " ".join(parts)


def _create(row: dict) -> Innovation:
    patent = row["patent"]
    name = patent["organizations"][0]
    organization = db.session.scalar(
        select(Organization).where(Organization.name == name).order_by(Organization.id).limit(1)
    )
    if organization is None:
        kind = "instytucja_publiczna" if name == LUKASIEWICZ else "uczelnia"
        organization = Organization(name=name, kind=kind)
    innovation = Innovation(
        title=row["title"], summary=row["summary"], description=_description(row),
        domains=row["domains"], organization=organization, kind="technologiczna",
        origin="radar", status="wykryta", claimed=False, structured_by="czlowiek",
        source_name=patent["source_name"], source_ref=patent["ref"], source_url=patent["url"],
        raw={"patent": patent, "manual_fields": ["summary", "stage", "results", "kind", "domains"]},
    )
    message = f"Radar dodał dokument {patent['ref']} po sprawdzeniu danych w publikacji urzędu."
    innovation.events.append(Event(type="wykryta", message=message, payload={
        "source_name": patent["source_name"], "source_ref": patent["ref"], "source_url": patent["url"],
    }))
    return innovation


def _relation(left: dict, right: dict) -> tuple[str, str] | None:
    same_office = left["source_name"] == right["source_name"]
    if same_office and left["application_id"] and left["application_id"] == right["application_id"]:
        return "same_application", f"Numer zgłoszenia {left['application_id']}."
    if not same_office:
        pl, ep = (left, right) if left["source_name"] == UPRP else (right, left)
        priority = {"application_id": pl["application_id"], "filing_date": pl["filing_date"]}
        if not ep["has_other_priorities"] and ep["priority_claims"] == [priority]:
            return "priority_claim", f"EPO wskazuje pierwszeństwo z {pl['application_id']} z datą {pl['filing_date']}."
    if {left["ref"], right["ref"]} == RELATED_MEASUREMENT:
        return "related_material", "Pokrewna tematyka pomiarów biomechanicznych. Związek wymaga sprawdzenia."
    return None


def _link(cards: list[Innovation]) -> None:
    documents = [(card, card.raw["patent"]) for card in cards]
    for card, patent in documents:
        links = []
        if notice := patent["grant_notice"]:
            links.append({
                "source_name": "UPRP · WUP", "ref": notice["ref"], "url": notice["url"],
                "relation": "grant_notice",
                "basis": f"Ogłoszenie o udzieleniu w WUP 11/2018 z dnia {notice['grant_announced_on']}.",
            })
        for other_card, other in documents:
            if card is other_card:
                continue
            if relation := _relation(patent, other):
                kind, basis = relation
                links.append({
                    "source_name": other["source_name"], "ref": other["ref"], "url": other["url"],
                    "innovation_id": other_card.id, "relation": kind, "basis": basis,
                })
        links.sort(key=lambda link: link["ref"])
        if links != patent.get("related_documents", []):
            card.raw = {**card.raw, "patent": {**patent, "related_documents": links}}
            if links:
                message = " ".join(
                    f"{'Materiał powiązany' if link['relation'] == 'related_material' else 'Powiązana publikacja'} "
                    f"{link['ref']}. {link['basis']}" for link in links
                )
                card.events.append(Event(type="powiazane_publikacje", message=message, payload={"documents": links}))


def run(source: str, limit: int = 20, *, new_only=False, refresh=False, cached_only=False) -> dict:
    if source not in SOURCES:
        raise PatentError("Wybierz źródło uprp_bup lub epo_eps.")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise PatentError("Limit importu musi być liczbą całkowitą od 1 do 50.")

    cache_dir = Path(current_app.config.get("PATENT_CACHE_DIR", CACHE_DIR)) / source
    started = monotonic()
    with run_lock(cache_dir):
        try:
            rows = collect(source, cache_dir, refresh=refresh, cached_only=cached_only)
            # Both offices can add links to the same row. Serialize the database phase across sources and processes.
            db.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('radar-patenty'))"))
            cards = list(db.session.scalars(
                select(Innovation).where(Innovation.source_name.in_(SOURCES)).order_by(Innovation.id)
            ))
            known = {card.source_ref for card in cards if card.source_name == source}
            new = [row for row in rows if row["patent"]["ref"] not in known]
            existing = [row for row in rows if row["patent"]["ref"] in known]
            selected = (new if new_only else new + existing)[:limit]
            additions = [_create(row) for row in new[:limit]]
            db.session.add_all(additions)
            db.session.flush()
            _link([card for card in cards if "patent" in (card.raw or {})] + additions)
            items = [{"id": card.id, "title": card.title} for card in additions]
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            if isinstance(exc, PatentError):
                write_json(cache_dir / "last-run.json", {
                    "finished_at": datetime.now(timezone.utc).isoformat(), "status": "error", "error": str(exc),
                })
            raise

        result = {
            "fetched": len(selected), "created": len(items), "skipped": len(selected) - len(items),
            "created_items": items, "missing_embeddings": len(items),
            "selection": {
                "complete_scan": True, "scanned": len(rows), "eligible": len(rows), "unavailable": [],
            },
        }
        write_json(cache_dir / "last-run.json", {
            "finished_at": datetime.now(timezone.utc).isoformat(), "status": "success",
            "duration_seconds": round(monotonic() - started, 2), **result,
        })
        return result
