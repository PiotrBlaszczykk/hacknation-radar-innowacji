import json
from time import monotonic

import click
from flask import Blueprint

from .. import processing

bp = Blueprint("processing", __name__)


@bp.cli.command("run")
@click.option("--dry-run", is_flag=True, help="Pokaż zakres i stan bez zapisu ani wywoływania modeli.")
@click.option("--limit", type=click.IntRange(min=1), help="Najwyżej tyle oczekujących kart w każdej fazie.")
def run_cli(dry_run: bool, limit: int | None) -> None:
    """Przetwórz karty w dwóch fazach. Ponowienie automatycznie wznawia zapisany stan."""
    start = monotonic()
    try:
        result = processing.run(click.echo, limit=limit, dry_run=dry_run)
    except processing.Busy as exc:
        raise click.ClickException(str(exc)) from exc
    result["sekundy"] = round(monotonic() - start, 2)
    click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["przerwano"]:
        raise click.ClickException("Model niedostępny. Ponów polecenie po przywróceniu modelu.")
    if result["bledy"] and not dry_run:
        raise click.ClickException("Nie wszystkie karty ukończono. Sprawdź błędy w raporcie i ponów polecenie.")
