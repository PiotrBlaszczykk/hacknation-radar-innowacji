from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from ... import domain
from ...extensions import db
from ...models import Event, Innovation, Organization
from ...services import embeddings, llm, structuring
from ..radon import run_lock, write_json
from .fetch import CACHE_DIR, SOURCE, InstitutionError, collect

TERMS_URL = (
    "https://bip.erzeszow.pl/319-informacja-publiczna-ponowne-wykorzystywanie-informacji-sektora-publicznego/"
    "4570-zasady-dostepu-do-informacji-publicznej.html"
)


def _record(row: dict, organization: Organization, draft: dict) -> Innovation:
    card = draft["card"]
    engines = draft["engine"]
    engine = " + ".join(dict.fromkeys(filter(None, engines.values())))
    publisher = row["site"].get("publisher", row["site"]["name"])
    domains = [key for key in (card.get("domains") or []) if key in domain.DOMAINS]
    if row["site"]["kind"] == "szkola" and "edukacja" not in domains:
        domains.insert(0, "edukacja")
    observed = row["observed_at"].split("T", 1)[0]
    published = f' Opublikowano {row["published"]}.' if row["published"] else ""
    attribution = (
        f'Wydawca źródła to {publisher}.{published} '
        f'Dostęp {observed}. Informacje opracowane przez Radar Innowacji.'
    )
    if row["site"]["id"] == "rzeszow":
        attribution += " Miasto Rzeszów nie odpowiada za opracowanie ani za dostępność, poprawność, aktualność lub kompletność informacji."
    innovation = Innovation(
        organization=organization,
        title=row["title"],
        description=f'{row["problem"]}\n\n{row["solution"]}\n\n{row["evidence"]}\n\n{attribution}',
        summary=row.get("summary") or card.get("summary") or row["solution"],
        problem=row["problem"],
        solution=row["solution"],
        results=row["evidence"],
        kind=card.get("kind") if card.get("kind") in domain.INNOVATION_KINDS else None,
        stage="wdrozona",
        domains=domains,
        support_needs=[key for key in (card.get("support_needs") or []) if key in domain.SUPPORT_NEEDS],
        keywords=card.get("keywords") or [],
        origin="radar",
        source_name=SOURCE,
        source_ref=row["ref"],
        source_url=row["url"],
        claimed=False,
        status="wykryta",
        structured_by=engine[:120],
        raw={
            "publisher": publisher,
            "observed_at": row["observed_at"],
            "published": row["published"],
            "evidence": row["evidence"],
            "is_innovation": draft["is_innovation"],
            "structuring_engine": engines,
            "structuring_version": draft.get("version"),
        },
    )
    innovation.events.append(Event(
        type="wykryta", message="Radar wykrył wdrożenie opisane przez instytucję. Karta zawiera propozycję modelu.",
        payload={"engine": engines, "evidence": row["evidence"]},
    ))
    return innovation


def run(
    cache_dir: Path, limit: int, *, new_only: bool = False, refresh: bool = False, cached_only: bool = False,
) -> dict:
    with run_lock(cache_dir):
        try:
            rows, stats = collect(cache_dir, refresh=refresh, cached_only=cached_only)
            if not rows and not stats["rejected"] and stats["unavailable"]:
                raise InstitutionError("Nie udało się potwierdzić wpisów. " + stats["unavailable"][0]["reason"])

            existing = set(db.session.scalars(
                select(Innovation.source_ref).where(Innovation.source_name == SOURCE)
            ))
            db.session.rollback()
            new = [row for row in rows if row["ref"] not in existing]
            known = [row for row in rows if row["ref"] in existing]
            selected = (new if new_only else new + known)[:limit]
            drafts = []
            for row in new[:limit]:
                draft = structuring.structure_text("\n\n".join(
                    row[key] for key in ("title", "problem", "solution", "evidence")
                ))
                if draft.get("version") != "2":
                    raise InstitutionError("Import kart wymaga strukturyzacji T10 w wersji 2.")
                drafts.append((row, draft))

            keys = {row["site"]["id"] for row, _ in drafts}
            organizations = {}
            if keys:
                query = select(Organization).where(Organization.external_ids[SOURCE].astext.in_(keys))
                organizations = {org.external_ids[SOURCE]: org for org in db.session.scalars(query)}
            records = []
            missing_embeddings = 0
            for row, draft in drafts:
                site = row["site"]
                key = site["id"]
                if key not in organizations:
                    organizations[key] = Organization(
                        name=site["name"], kind=site["kind"], city=site["city"], region="podkarpackie",
                        website=site["origin"], external_ids={SOURCE: key},
                    )
                innovation = _record(row, organizations[key], draft)
                missing_embeddings += not embeddings.try_embed(innovation)
                db.session.add(innovation)
                records.append(innovation)

            db.session.flush()
            items = [{"id": item.id, "title": item.title} for item in records]
            db.session.commit()
            result = {
                "fetched": len(selected),
                "created": len(items),
                "skipped": len(selected) - len(items),
                "created_items": items,
                "missing_embeddings": missing_embeddings,
                "selection": stats,
            }
        except (InstitutionError, llm.LLMUnavailable) as exc:
            db.session.rollback()
            write_json(cache_dir / "last-run.json", {
                "finished_at": datetime.now(timezone.utc).isoformat(), "status": "error", "error": str(exc),
            })
            raise

        write_json(cache_dir / "last-run.json", {
            "finished_at": datetime.now(timezone.utc).isoformat(), "status": "success", **result,
        })
        return result
