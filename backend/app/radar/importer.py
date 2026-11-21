import json
from datetime import datetime, timezone
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from time import monotonic

from sqlalchemy import func, select

from ..extensions import db
from ..models import Event, Innovation, Organization
from ..services import embeddings
from . import instytucje, projekty_publiczne
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
        "name": instytucje.SOURCE,
        "title": "Strony instytucji",
        "description": "Udokumentowane wdrożenia opisane przez szkoły i samorządy Podkarpacia.",
        "url": None,
        "terms": "Warunki ponownego wykorzystywania · Miasto Rzeszów",
        "terms_url": instytucje.TERMS_URL,
        "status": "aktywne",
        "rules": [
            "Jawna lista witryn i wpisów z przeglądem faktów przed importem.",
            "Wymagany opis zastosowania w lokalnej instytucji. Pomijamy ogłoszenia i relacje bez dowodu zastosowania.",
            "Model przygotowuje propozycję karty. Karta zawiera źródło i fakt o wdrożeniu.",
        ],
    },
    *projekty_publiczne.SOURCES,
)

patent_module = f"{__package__}.patenty"
patent_spec = find_spec(patent_module)
patenty = import_module(patent_module) if patent_spec and patent_spec.origin else None

PATENT_SOURCES = (
    {
        "name": "uprp_bup", "title": "UPRP · Biuletyn Urzędu Patentowego",
        "description": "Opublikowane zgłoszenia z Biuletynu Urzędu Patentowego RP.",
        "url": "https://uprp.gov.pl/pl/publikacje/biuletyn-i-wiadomosci-uprp",
        "terms": "Metadane zgłoszenia i odnośnik do biuletynu.",
        "terms_url": None,
        "rules": ["Publikacja zgłoszenia wskazuje rozwiązanie techniczne i nie potwierdza wdrożenia."],
    },
    {
        "name": "epo_eps", "title": "EPO · European Publication Server",
        "description": "Europejskie dokumenty patentowe i metadane publikacji.",
        "url": "https://data.epo.org/publication-server/",
        "terms": "Warunki korzystania z witryny EPO.",
        "terms_url": "https://www.epo.org/en/terms-of-use/terms-and-conditions-use-website-european-patent-office",
        "rules": ["Status i identyfikator pochodzą z dokumentu EPO. Datę i etap wdrożenia ustala broker."],
    },
)
PATENT_NAMES = tuple(source["name"] for source in PATENT_SOURCES)
PUBLIC_NAMES = tuple(source["name"] for source in projekty_publiczne.SOURCES)
SOURCE_NAMES = (SOURCE, instytucje.SOURCE, *PUBLIC_NAMES, *PATENT_NAMES)


def _last_run_path(cache_dir: Path) -> Path:
    return cache_dir / "last-run.json"


def _read_stats(path: Path) -> dict | None:
    try:
        stats = json.loads(path.read_bytes())
    except (FileNotFoundError, ValueError):
        return None
    return stats if isinstance(stats, dict) else None


def list_sources(
    cache_dir: Path, institutions_cache: Path = instytucje.CACHE_DIR,
    public_cache: Path = projekty_publiczne.CACHE_DIR, patent_cache: Path | None = None,
) -> list[dict]:
    decision = Innovation.raw["radar_review"]["decision"].astext
    totals = {
        name: (count, reviewed, rejected)
        for name, count, reviewed, rejected in db.session.execute(
            select(
                Innovation.source_name,
                func.count(),
                func.count().filter(decision.is_not(None)),
                func.count().filter(decision == "odrzucona"),
            )
            .where(Innovation.origin == "radar")
            .group_by(Innovation.source_name)
        )
    }
    last_runs = {
        SOURCE: _read_stats(_last_run_path(cache_dir)),
        instytucje.SOURCE: _read_stats(institutions_cache / "last-run.json"),
    }
    last_runs.update({name: _read_stats(public_cache / name / "last-run.json") for name in PUBLIC_NAMES})
    if patenty is not None:
        root = patent_cache or patenty.CACHE_DIR
        last_runs.update({name: _read_stats(root / name / "last-run.json") for name in PATENT_NAMES})
    linked = db.session.scalar(
        select(func.count()).select_from(Innovation).where(
            Innovation.raw["publications"].contains([{"metadata_source": "crossref", "relationship": "verified_use"}]),
        ),
    )
    totals["crossref"] = (linked, 0, 0)
    scan = _read_stats(cache_dir / "last-scan.json")
    if scan is None:
        scan = (last_runs[SOURCE] or {}).get("selection")
    items = []
    patent_status = "aktywne" if patenty is not None else "planowane"
    for source in (*SOURCES, *({**entry, "status": patent_status} for entry in PATENT_SOURCES)):
        name = source["name"]
        count, reviewed, rejected = totals.get(name, (0, 0, 0))
        item = {**source, "count": count, "last_run": last_runs.get(name)}
        if name == SOURCE:
            item["statistics"] = {
                "scanned": scan.get("scanned") if scan else None,
                "complete_scan": scan.get("complete_scan") if scan else None,
                "reviewed": reviewed, "rejected": rejected,
            }
        items.append(item)
    return items


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
        previous = (_read_stats(_last_run_path(cache_dir)) or {}).get("selection", {})
        if previous.get("complete_scan") and not (cache_dir / "last-scan.json").exists():
            write_json(cache_dir / "last-scan.json", previous)
        try:
            query = select(Innovation.source_ref).where(Innovation.source_name == SOURCE)
            existing = set(db.session.scalars(query))
            db.session.rollback()

            with http_client() as http:
                client = RadonClient(http, cache_dir, refresh=refresh, cached_only=cached_only)
                candidates, counts = collect(client, known=existing, demo_limit=limit if new_only else None)

            projekty_publiczne.lock_project_writes()
            public_keys = {
                projekty_publiczne.project_key(raw["public_project"]["source_title"], organization)
                for raw, organization in db.session.execute(
                    select(Innovation.raw, Organization.name)
                    .join(Organization, Innovation.organization_id == Organization.id)
                    .where(Innovation.source_name.in_(("interreg", "ncbr")))
                )
                if (raw or {}).get("public_project", {}).get("source_title")
            }
            eligible = [
                row for row in candidates
                if row.ref in existing or projekty_publiczne.project_key(row.title, row.leader_name) not in public_keys
            ]
            if new_only:
                selected = [row for row in eligible if row.ref not in existing][:limit]
            else:
                regional = [row for row in eligible if row.regional]
                other = [row for row in eligible if not row.regional]
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
                    "cross_source_duplicates": len(candidates) - len(eligible),
                },
            }
        except RadonError as exc:
            write_json(_last_run_path(cache_dir), {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "error": str(exc),
            })
            raise

        if counts["complete_scan"]:
            write_json(cache_dir / "last-scan.json", result["selection"])
        write_json(_last_run_path(cache_dir), {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(monotonic() - started, 2),
            "status": "success",
            **{key: result[key] for key in ("fetched", "created", "skipped", "missing_embeddings", "selection")},
        })
        return result
