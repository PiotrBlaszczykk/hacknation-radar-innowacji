import hashlib
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import create_app
from app.config import EMBED_DIM, Config
from app.extensions import db
from app.seed import load_seed
from app.services import decisions, llm

# Każde uruchomienie testów dostaje własną bazę: nie rusza danych deweloperskich
# i nie koliduje z testami puszczonymi równolegle przez kogoś innego.
DEV_URL = make_url(Config.SQLALCHEMY_DATABASE_URI)
TEST_DB = f"{DEV_URL.database}_test_{os.getpid()}"
TEST_URL = DEV_URL.set(database=TEST_DB)


@pytest.fixture(scope="session", autouse=True)
def test_database():
    admin = create_engine(DEV_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    yield
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    admin.dispose()


def fake_embed(texts: list[str], **_) -> list[list[float]]:
    """Deterministyczny wektor z treści: ten sam tekst daje ten sam wektor, bez modelu."""
    vectors = []
    for item in texts:
        digest = hashlib.sha256(item.encode()).digest()
        vectors.append([(digest[i % len(digest)] - 127.5) / 127.5 for i in range(EMBED_DIM)])
    return vectors


@pytest.fixture(autouse=True)
def offline_models(monkeypatch):
    """Testy nie wołają prawdziwych modeli. Odpowiedzi podmień w teście przez monkeypatch
    (llm.chat_json, decisions.decide albo decisions.decide_one)."""

    def no_chat(*args, **kwargs):
        raise llm.LLMUnavailable("Model wyłączony w testach")

    monkeypatch.setattr(llm, "embed", fake_embed)
    monkeypatch.setattr(llm, "chat_json", no_chat)
    monkeypatch.setattr(decisions, "_ask_codes", no_chat)


@pytest.fixture()
def app(offline_models):
    app = create_app(
        {"TESTING": True, "BASAL_URL": "", "SQLALCHEMY_DATABASE_URI": TEST_URL.render_as_string(hide_password=False)}
    )
    with app.app_context():
        db.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.session.commit()
        db.drop_all()
        db.create_all()
        load_seed()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()
