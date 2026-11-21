import json
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from sqlalchemy import func, select

from ..extensions import db
from ..models import Event, Innovation, Organization
from ..services import embeddings
from .radon import (
    PROJECTS_URL, SOURCE, RadonClient, RadonError, http_client, profile_url, run_lock, write_json,
)
from .selection import RULES, Candidate, collect, organization_fields, summary

TERMS_URL = "https://radon.nauka.gov.pl/citizen-data-api/account/terms/40?lang=pl"
SOURCES = (
    {
        "name": SOURCE,
        "title": "RAD-on · Projekty naukowe",
        "description": "Publiczny rejestr projektów badawczych i rozwojowych zgłaszanych do POL-on.",
        "url": PROJECTS_URL,
        "terms": "Publiczne API RAD-on. Obowiązuje regulamin serwisu.",
        "terms_url": TERMS_URL,
        "status": "aktywne",
        "rules": RULES,
    },
    {
        "name": "strony_instytucji",
        "title": "Strony instytucji",
        "description": "Aktualności szkół, urzędów, uczelni i innych instytucji publicznych.",
        "url": None,
        "terms": "Warunki ustalane dla każdej witryny.",
        "terms_url": None,
        "status": "planowane",
        "rules": [],
    },
    {
        "name": "ncbr",
        "title": "NCBR",
        "description": "Wyszukiwarka sukcesów beneficjentów Narodowego Centrum Badań i Rozwoju.",
        "url": "https://www.gov.pl/web/ncbr/wyszukiwarka-sukcesow-beneficjentow",
        "terms": "Zasady ponownego wykorzystywania informacji NCBR.",
        "terms_url": "https://www.gov.pl/web/ncbr/ponowne-wykorzystywanie-informacji-sektora-publicznego",
        "status": "planowane",
        "rules": [],
    },
    {
        "name": "interreg",
        "title": "Interreg",
        "description": "Lista projektów współpracy transgranicznej, transnarodowej i międzyregionalnej.",
        "url": "https://interreg.gov.pl/lista-projektow/",
        "terms": "Warunki publikowane przez Interreg.",
        "terms_url": None,
        "status": "planowane",
        "rules": [],
    },
)


def _last_run_path(cache_dir: Path) -> Path:
    return cache_dir / "last-run.json"


def list_sources(cache_dir: Path) -> list[dict]:
    totals = dict(db.session.execute(
        select(Innovation.source_name, func.count())
        .where(Innovation.origin == "radar")
        .group_by(Innovation.source_name)
    ).all())
    try:
        last_run = json.loads(_last_run_path(cache_dir).read_bytes())
    except (FileNotFoundError, ValueError):
        last_run = None
    return [
        {**source, "count": totals.get(source["name"], 0), "last_run": last_run if source["name"] == SOURCE else None}
        for source in SOURCES
    ]


def _record(candidate: Candidate, organizations: dict[str, Organization]) -> Innovation:
    organization = organizations.get(candidate.leader_id)
    if organization is None:
        organization = Organization(**organization_fields(candidate))
        organizations[candidate.leader_id] = organization
    innovation = Innovation(
        organization=organization,
        title=candidate.title,
        description=candidate.description,
        summary=summary(candidate.description),
        keywords=candidate.keywords,
        origin="radar",
        source_name=SOURCE,
        source_ref=candidate.ref,
        source_url=profile_url(candidate.ref),
        claimed=False,
        status="wykryta",
        structured_by=None,
        raw=candidate.raw,
    )
    innovation.events.append(Event(type="wykryta", message="Radar wykrył projekt w publicznym rejestrze RAD-on."))
    return innovation


def run(
    cache_dir: Path, limit: int, *, new_only: bool = False, refresh: bool = False, cached_only: bool = False,
) -> dict:
    started = monotonic()
    with run_lock(cache_dir):
        try:
            query = select(Innovation.source_ref).where(Innovation.source_name == SOURCE)
            existing = set(db.session.scalars(query))
            db.session.rollback()

            with http_client() as http:
                client = RadonClient(http, cache_dir, refresh=refresh, cached_only=cached_only)
                candidates, counts = collect(client, known=existing, demo_limit=limit if new_only else None)

            if new_only:
                selected = [row for row in candidates if row.ref not in existing][:limit]
            else:
                regional = candidates[:counts["eligible_regional"]]
                other = candidates[counts["eligible_regional"]:]
                already_selected = [row for row in other if row.ref in existing]
                unselected = [row for row in other if row.ref not in existing]
                regular_slots = max(0, limit - len(regional) - len(existing - {row.ref for row in candidates}))
                selected = regional + (already_selected + unselected)[:regular_slots]

            additions = [row for row in selected if row.ref not in existing]
            organizations = {}
            if additions:
                keys = {row.leader_id for row in additions}
                query = (
                    select(Organization)
                    .where(Organization.external_ids["radon"].astext.in_(keys))
                    .order_by(Organization.id.desc())
                )
                organizations = {org.external_ids["radon"]: org for org in db.session.scalars(query)}

            created = []
            missing_embeddings = 0
            for row in additions:
                innovation = _record(row, organizations)
                if not embeddings.try_embed(innovation):
                    missing_embeddings += 1
                db.session.add(innovation)
                created.append(innovation)
            db.session.flush()
            items = [{"id": item.id, "title": item.title} for item in created]
            db.session.commit()

            result = {
                "fetched": len(selected),
                "created": len(items),
                "skipped": len(selected) - len(items),
                "created_items": items,
                "missing_embeddings": missing_embeddings,
                "selection": {
                    **counts,
                    "selected_regional": sum(row.regional for row in selected),
                    "created_regional": sum(row.regional for row in additions),
                },
            }
        except RadonError as exc:
            write_json(_last_run_path(cache_dir), {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "error": str(exc),
            })
            raise

        write_json(_last_run_path(cache_dir), {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(monotonic() - started, 2),
            "status": "success",
            **{key: result[key] for key in ("fetched", "created", "skipped", "missing_embeddings", "selection")},
        })
        return result
