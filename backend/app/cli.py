import click
from flask import Flask
from sqlalchemy import text

from .extensions import db


def register_cli(app: Flask) -> None:
    @app.cli.command("db-reset")
    def db_reset():
        """Kasuje tabele, tworzy schemat od nowa i ładuje dane startowe."""
        from .seed import load_seed

        db.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.session.commit()
        db.drop_all()
        db.create_all()
        click.echo("Schemat utworzony.")
        click.echo(load_seed())
        click.echo(_embed_all())

    @app.cli.command("seed")
    def seed():
        """Ładuje dane startowe do istniejącego schematu (pomija, jeśli już są)."""
        from .seed import load_seed

        click.echo(load_seed())

    @app.cli.command("embed")
    def embed():
        """Liczy embeddingi dla rekordów, które ich nie mają."""
        click.echo(_embed_all())


def _embed_all() -> str:
    from .models import Innovation, Need, User
    from .services import embeddings
    from .services.llm import LLMUnavailable

    try:
        done = {model.__tablename__: embeddings.embed_missing(model) for model in (Innovation, Need, User)}
    except LLMUnavailable as e:
        return f"Embeddingi pominięte: {e}"
    return "Embeddingi policzone: " + ", ".join(f"{name}: {count}" for name, count in done.items())
