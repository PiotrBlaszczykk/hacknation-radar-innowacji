from pathlib import Path
from time import monotonic

import click
from flask import Blueprint, abort, current_app, jsonify

from ..extensions import db
from ..radar import enrichment, importer
from ..radar.radon import CACHE_DIR, SOURCE, RadarBusy, RadonError
from ..services.llm import LLMUnavailable
from .common import json_body

bp = Blueprint("radar", __name__)


def _cache_dir() -> Path:
    return Path(current_app.config.get("RADON_CACHE_DIR", CACHE_DIR))


@bp.get("/radar/sources")
def sources():
    return jsonify(items=importer.list_sources(_cache_dir()))


@bp.post("/radar/run")
def run():
    data = json_body()
    if data.get("source") != SOURCE:
        abort(400, "Wybierz aktywne źródło radaru.")
    limit = data.get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= 50:
        abort(400, "Limit musi być liczbą całkowitą od 1 do 50.")
    try:
        return jsonify(importer.run(_cache_dir(), limit, new_only=True))
    except RadarBusy as exc:
        abort(409, str(exc))
    except RadonError as exc:
        abort(503, str(exc))


@bp.cli.command("run")
@click.option("--source", type=click.Choice([SOURCE]), default=SOURCE, show_default=True)
@click.option("--limit", type=click.IntRange(min=1), default=500, show_default=True)
@click.option("--refresh", is_flag=True, help="Pobierz aktualne strony zamiast używać zapisanych kopii.")
@click.option("--cached-only", is_flag=True, help="Użyj wyłącznie dostępnych stron z lokalnej pamięci.")
def run_cli(source: str, limit: int, refresh: bool, cached_only: bool) -> None:
    if refresh and cached_only:
        raise click.UsageError("Wybierz jedno z: --refresh, --cached-only.")
    try:
        result = importer.run(_cache_dir(), limit, refresh=refresh, cached_only=cached_only)
    except RadonError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f'{source} — wybrano {result["fetched"]}, dodano {result["created"]}, pominięto {result["skipped"]}.'
    )
    if not result["selection"]["complete_scan"]:
        click.echo("Przejrzano dostępną część źródła w lokalnej pamięci.")
    click.echo(
        f'Kwalifikacja — {result["selection"]}. Bez embeddingu — {result["missing_embeddings"]}.'
    )


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
