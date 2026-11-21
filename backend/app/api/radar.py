from pathlib import Path
from time import monotonic

import click
from flask import Blueprint, abort, current_app, jsonify

from ..extensions import db
from ..radar import enrichment, importer, instytucje, projekty_publiczne
from ..radar.radon import CACHE_DIR, SOURCE, RadarBusy, RadonError, run_lock
from ..services.llm import LLMUnavailable
from .common import json_body

bp = Blueprint("radar", __name__)


def _cache_dir() -> Path:
    return Path(current_app.config.get("RADON_CACHE_DIR", CACHE_DIR))


def _institutions_cache() -> Path:
    return Path(current_app.config.get("INSTITUTIONS_CACHE_DIR", instytucje.CACHE_DIR))


def _public_cache() -> Path:
    return Path(current_app.config.get("PUBLIC_PROJECTS_CACHE_DIR", projekty_publiczne.CACHE_DIR))


def _run_source(source: str, limit: int, **options) -> dict:
    if source == SOURCE:
        return importer.run(_cache_dir(), limit, **options)
    if source == instytucje.SOURCE:
        return instytucje.run(_institutions_cache(), limit, **options)
    if source in importer.PUBLIC_NAMES:
        return projekty_publiczne.run(source, _public_cache(), limit, **options)

    adapter = importer.patenty
    if adapter is None:
        raise projekty_publiczne.PublicSourceError("Adapter patentowy jest niedostępny.")
    try:
        return adapter.run(source, limit, **options)
    except adapter.PatentError as exc:
        raise projekty_publiczne.PublicSourceError(str(exc)) from exc


@bp.get("/radar/sources")
def sources():
    patent_cache = current_app.config.get("PATENT_CACHE_DIR")
    return jsonify(items=importer.list_sources(
        _cache_dir(), _institutions_cache(), _public_cache(), Path(patent_cache) if patent_cache else None,
    ))


@bp.post("/radar/run")
def run():
    data = json_body()
    source = data.get("source")
    if source not in importer.SOURCE_NAMES:
        abort(400, "Wybierz aktywne źródło radaru.")
    limit = data.get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= 50:
        abort(400, "Limit musi być liczbą całkowitą od 1 do 50.")
    refresh, cached_only = data.get("refresh", False), data.get("cached_only", False)
    if type(refresh) is not bool or type(cached_only) is not bool or (refresh and cached_only):
        abort(400, "Wybierz co najwyżej jedną z opcji refresh i cached_only.")
    try:
        return jsonify(_run_source(source, limit, new_only=True, refresh=refresh, cached_only=cached_only))
    except RadarBusy as exc:
        abort(409, str(exc))
    except (RadonError, instytucje.InstitutionError, projekty_publiczne.PublicSourceError, LLMUnavailable) as exc:
        abort(503, str(exc))


@bp.cli.command("run")
@click.option("--source", type=click.Choice(importer.SOURCE_NAMES), default=SOURCE, show_default=True)
@click.option("--limit", type=click.IntRange(min=1), help="Domyślnie 500 dla starszych źródeł i 20 dla pozostałych.")
@click.option("--refresh", is_flag=True, help="Pobierz aktualne strony zamiast używać zapisanych kopii.")
@click.option("--cached-only", is_flag=True, help="Użyj wyłącznie dostępnych stron z lokalnej pamięci.")
def run_cli(source: str, limit: int | None, refresh: bool, cached_only: bool) -> None:
    if refresh and cached_only:
        raise click.UsageError("Wybierz jedno z: --refresh, --cached-only.")
    if limit is None:
        limit = 500 if source in (SOURCE, instytucje.SOURCE) else 20
    try:
        result = _run_source(source, limit, refresh=refresh, cached_only=cached_only)
    except (RadonError, instytucje.InstitutionError, projekty_publiczne.PublicSourceError, LLMUnavailable) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f'{source} — wybrano {result["fetched"]}, dodano {result["created"]}, pominięto {result["skipped"]}.'
    )
    if "updated" in result:
        click.echo(f'Powiązano publikację z kartami — {result["updated"]}.')
    for item in result["created_items"] + result.get("updated_items", []):
        click.echo(f'{item["id"]} · {item["title"]}')
    if not result["selection"]["complete_scan"]:
        click.echo("Przegląd źródła był częściowy.")
    click.echo(
        f'Kwalifikacja — {result["selection"]}. Bez embeddingu — {result["missing_embeddings"]}.'
    )


@bp.cli.command("scan-institutions")
@click.option("--refresh", is_flag=True, help="Pobierz aktualne wersje stron.")
@click.option("--cached-only", is_flag=True, help="Odczytaj zapisane obserwacje bez dostępu do sieci.")
def scan_institutions_cli(refresh: bool, cached_only: bool) -> None:
    """Sprawdź listy i wpisy instytucji bez uruchamiania modeli i zapisu kart."""
    if refresh and cached_only:
        raise click.UsageError("Wybierz jedno z: --refresh, --cached-only.")
    try:
        with run_lock(_institutions_cache()):
            rows, stats = instytucje.collect(_institutions_cache(), refresh=refresh, cached_only=cached_only)
    except (instytucje.InstitutionError, RadarBusy) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f'Przejrzano {stats["scanned"]}, potwierdzono {stats["eligible"]}, odrzucono {len(stats["rejected"])}.')
    for row in rows:
        click.echo(f'{row["url"]} · {row["title"]}')
    for category in ("rejected", "unavailable"):
        label = "Pominięto" if category == "rejected" else "Brak weryfikacji"
        for row in stats[category]:
            click.echo(f'{label} · {row["url"]} · {row["reason"]}')


@bp.cli.command("enrich")
@click.option("--limit", type=click.IntRange(min=1), default=50, show_default=True)
def enrich_cli(limit: int) -> None:
    try:
        from ..services.structuring import structure_text
    except ModuleNotFoundError as exc:
        if exc.name != "app.services.structuring":
            raise
        click.echo("Usługa uzupełniania kart z zadania T02 jest jeszcze niedostępna.")
        return

    started = monotonic()
    done = 0
    try:
        for done, innovation_id in enumerate(enrichment.enrich(limit, structure_text), start=1):
            click.echo(f"{done}/{limit} · karta {innovation_id} · {monotonic() - started:.1f} s od startu")
    except LLMUnavailable as exc:
        db.session.rollback()
        raise click.ClickException(f"Model jest niedostępny. Zapisano {done} kart.") from exc
    click.echo(f"Uzupełniono {done} kart w {monotonic() - started:.1f} s.")
