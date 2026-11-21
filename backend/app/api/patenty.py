import json

import click
from flask import Blueprint

from ..radar import patenty
from ..radar.radon import RadarBusy
from ..radar.patenty.catalog import SOURCES

bp = Blueprint("patenty", __name__)


@bp.cli.command("run")
@click.option("--source", type=click.Choice(SOURCES), required=True)
@click.option("--limit", type=click.IntRange(1, 50), default=20, show_default=True)
@click.option("--refresh", is_flag=True, help="Pobierz i zweryfikuj dokumenty urzędów.")
@click.option("--cached-only", is_flag=True, help="Odczytaj kopię metadanych w trybie offline.")
def run_cli(source: str, limit: int, refresh: bool, cached_only: bool) -> None:
    """Zaimportuj sprawdzoną partię publikacji z wybranego urzędu."""
    try:
        result = patenty.run(source, limit, refresh=refresh, cached_only=cached_only)
    except (patenty.PatentError, RadarBusy) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, ensure_ascii=False))
