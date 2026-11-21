import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, time
from unicodedata import normalize

import yaml
from sqlalchemy import select, text

from ...extensions import db
from ...models import Event, Innovation, Organization
from ..radon import SOURCE as RADON_SOURCE
from ..radon import run_lock, write_json
from .collect import CROSSREF_URL, INTERREG_URL, NCBR_URL, PublicSourceError, collect

CACHE_DIR = Path(__file__).resolve().parents[4] / "data/cache/projekty_publiczne"
REVIEWS = Path(__file__).with_name("reviews.yaml")
NCBR_TERMS = "https://www.gov.pl/web/ncbr/ponowne-wykorzystywanie-informacji-sektora-publicznego"
CACHE_AGE = 86_400
SOURCES = (
    {
        "name": "ncbr", "title": "NCBR · Sukcesy beneficjentów", "url": NCBR_URL,
        "description": "Zastosowania opisane przez beneficjentów NCBR w szkołach, na uczelniach i w usługach publicznych.",
        "terms": "Fakty we własnym opracowaniu z oznaczeniem źródła i czasu pozyskania.",
        "terms_url": NCBR_TERMS, "status": "aktywne",
        "rules": ["Weryfikacja faktu zastosowania na stronie projektu oraz rozróżnienie beneficjenta i odbiorców."],
    },
    {
        "name": "interreg", "title": "Interreg · Projekty", "url": INTERREG_URL,
        "description": "Rozwiązania dla sektora publicznego z wykazu projektów i kart programu Interreg.",
        "terms": "Wykaz opublikowany do ponownego wykorzystania na podstawie art. 49 rozporządzenia 2021/1060.",
        "terms_url": "https://eur-lex.europa.eu/eli/reg/2021/1060/oj?locale=pl", "status": "aktywne",
        "rules": ["Wykaz XLSX identyfikuje projekt i partnera wiodącego. Strona programu potwierdza zastosowanie i jego etap."],
    },
    {
        "name": "crossref", "title": "Crossref · Powiązane publikacje", "url": CROSSREF_URL,
        "description": "Metadane DOI z Crossref i dowód użycia rozwiązania na stronie wydawcy. Licznik podaje liczbę kart z powiązaniem.",
        "terms": "Metadane bibliograficzne Crossref do ponownego użycia.",
        "terms_url": "https://www.crossref.org/documentation/retrieve-metadata/#licensing", "status": "aktywne",
        "rules": ["Publikacja uzupełnia istniejącą kartę wyłącznie po potwierdzeniu związku w treści artykułu."],
    },
)


def _load_observations(source: str, directory: Path, *, refresh: bool, cached_only: bool) -> dict:
    path = directory / "observations.json"
    config = REVIEWS.read_bytes()
    fingerprint = hashlib.sha256(config).hexdigest()
    if not refresh:
        try:
            if cached_only or time() - path.stat().st_mtime < CACHE_AGE:
                data = json.loads(path.read_bytes())
                if data.get("fingerprint") == fingerprint:
                    return data
        except (OSError, ValueError, AttributeError):
            pass
    if cached_only:
        raise PublicSourceError("Brak aktualnych obserwacji w lokalnej pamięci. Uruchom radar z dostępem do sieci.")
    data = collect(source, yaml.safe_load(config)[source])
    write_json(path, {**data, "fingerprint": fingerprint})
    return data


def identity(value: str | None) -> str:
    return " ".join(re.findall(r"[^\W_]+", normalize("NFKC", value or "").casefold()))


def project_key(title: str, lead: str) -> tuple[str, str]:
    return identity(title), identity(lead)


def lock_project_writes() -> None:
    # Blokada transakcyjna wspólna dla nowych kart RAD-on i projektów publicznych.
    db.session.execute(text("SELECT pg_advisory_xact_lock(19207371)"))


def _import_projects(source: str, observations: dict, limit: int, *, new_only: bool) -> dict:
    lock_project_writes()
    projects = db.session.execute(
        select(Innovation, Organization.name)
        .outerjoin(Organization, Innovation.organization_id == Organization.id)
        .where(Innovation.source_name.in_((RADON_SOURCE, "interreg", "ncbr")))
        .order_by(Innovation.id)
    ).all()
    same_source = {item.source_ref for item, _ in projects if item.source_name == source}
    already_linked = {
        (item.raw or {}).get("related_public_projects", {}).get(source, {}).get("ref") for item, _ in projects
    }
    known = (same_source | already_linked) - {None}
    new_rows = [row for row in observations["rows"] if row["ref"] not in known]
    existing_rows = [row for row in observations["rows"] if row["ref"] in known]
    selected = new_rows if new_only else new_rows + existing_rows
    keys = {}
    for item, organization in projects:
        if organization:
            original_title = (item.raw or {}).get("public_project", {}).get("source_title") or item.title
            keys.setdefault(project_key(original_title, organization), item)
    organizations = {
        identity(organization.name): organization
        for organization in db.session.scalars(select(Organization).order_by(Organization.id.desc()))
    }
    created = []
    seen = set()
    skipped = duplicates = fetched = 0
    for row in selected:
        ref = row["ref"]
        if ref in seen:
            continue
        seen.add(ref)
        if fetched >= limit:
            break
        fetched += 1
        if ref in known:
            skipped += 1
            continue
        key = project_key(row["source_title"], row["organization"])
        if key in keys:
            duplicates += 1
            skipped += 1
            existing = keys[key]
            raw = existing.raw or {}
            references = raw.get("related_public_projects", {})
            if references.get(source, {}).get("ref") != ref:
                existing.raw = {
                    **raw, "related_public_projects": {**references, source: {"ref": ref, "url": row["url"]}},
                }
                existing.events.append(Event(
                    type="zrodlo", message=f"Dodatkowe źródło projektu · {row['url']}",
                    payload={"source": source, "ref": ref, "url": row["url"]},
                ))
            continue
        organization_key = identity(row["organization"])
        organization = organizations.get(organization_key)
        if organization is None:
            organization = Organization(
                name=row["organization"], kind=row["organization_kind"], city=row.get("city"),
                region=row.get("region"), interests=row["domains"],
            )
            organizations[organization_key] = organization
        innovation = Innovation(
            organization=organization, title=row["title"], summary=row["solution"],
            description=f"{row['problem']}\n\n{row['solution']}\n\nOdbiorcy: {row['recipients']}.",
            problem=row["problem"], solution=row["solution"], results=row["evidence"],
            kind=row["kind"], stage=row["stage"], domains=row["domains"],
            origin="radar", source_name=source, source_ref=ref, source_url=row["url"],
            claimed=False, status="wykryta",
            raw={
                "public_project": {
                    **row["locator"], "source_title": row["source_title"], "recipients": row["recipients"],
                    "observed_at": observations["observed_at"],
                },
                "evidence": row["evidence"], "manual_fields": ["summary", "problem", "solution", "results", "stage"],
            },
        )
        innovation.events.append(Event(
            type="wykryta", message="Radar wykrył udokumentowane zastosowanie w publicznym źródle.",
            payload={"source": source, "ref": ref, "url": row["url"]},
        ))
        db.session.add(innovation)
        keys[key] = innovation
        created.append(innovation)
    db.session.flush()
    items = [{"id": item.id, "title": item.title} for item in created]
    db.session.commit()
    return {
        "fetched": fetched, "created": len(items), "skipped": skipped, "created_items": items,
        "missing_embeddings": len(items),
        "selection": {**observations["selection"], "cross_source_duplicates": duplicates},
    }


def _link_publications(observations: dict, limit: int, *, new_only: bool) -> dict:
    updated = []
    skipped = fetched = without_card = 0
    for row in observations["rows"]:
        if fetched >= limit:
            break
        project = db.session.scalar(
            select(Innovation).where(
                ((Innovation.source_name == "ncbr") & (Innovation.source_ref == row["project_ref"]))
                | (Innovation.raw["related_public_projects"]["ncbr"]["ref"].astext == row["project_ref"]),
            ).order_by(Innovation.id).limit(1).with_for_update()
        )
        if project is None:
            without_card += 1
            fetched += 1
            skipped += 1
            continue
        publications = (project.raw or {}).get("publications", [])
        if any(item.get("doi", "").casefold() == row["doi"] for item in publications):
            if not new_only:
                fetched += 1
                skipped += 1
            continue
        fetched += 1
        citation = {key: value for key, value in row.items() if key != "project_ref"}
        project.raw = {**(project.raw or {}), "publications": [*publications, citation]}
        project.description = (
            f"{(project.description or '').rstrip()}\n\n"
            f"Powiązana publikacja: {row['title']} ({row['publisher']}). DOI: {row['doi']}. "
            f"Metadane: Crossref. {row['evidence']}"
        ).strip()
        project.events.append(Event(
            type="zrodlo", message=f"Potwierdzono użycie rozwiązania w publikacji · DOI {row['doi']}.", payload=citation,
        ))
        updated.append({"id": project.id, "title": project.title})
    db.session.commit()
    return {
        "fetched": fetched, "created": 0, "skipped": skipped, "created_items": [], "missing_embeddings": 0,
        "updated": len(updated), "updated_items": updated,
        "selection": {**observations["selection"], "without_card": without_card},
    }


def run(
    source: str, cache_dir: Path, limit: int, *, new_only: bool = False, refresh: bool = False, cached_only: bool = False,
) -> dict:
    started = monotonic()
    directory = cache_dir / source
    with run_lock(cache_dir):
        directory.mkdir(exist_ok=True)
        path = directory / "last-run.json"
        try:
            observations = _load_observations(source, directory, refresh=refresh, cached_only=cached_only)
            if source == "crossref":
                result = _link_publications(observations, limit, new_only=new_only)
            else:
                result = _import_projects(source, observations, limit, new_only=new_only)
        except PublicSourceError as exc:
            title = next(item["title"] for item in SOURCES if item["name"] == source)
            message = f"Źródło {title} jest niedostępne. {exc}"
            write_json(path, {"finished_at": datetime.now(timezone.utc).isoformat(), "status": "error", "error": message})
            raise PublicSourceError(message) from exc
        write_json(path, {
            **{key: value for key, value in result.items() if not key.endswith("_items")},
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(monotonic() - started, 2),
            "status": "success",
        })
        return result
