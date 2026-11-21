from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.extensions import db

DEMO_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "demo"


def test_demo_guard_refuses_other_database(app):
    with app.app_context(), pytest.raises(DBAPIError, match="Cel nie jest oznaczoną bazą pokazową T14"):
        db.session.execute(text((DEMO_SCRIPTS / "guard.sql").read_text()))


def test_demo_fixtures_refuse_unknown_source_snapshot(app):
    with app.app_context(), pytest.raises(DBAPIError, match="Nie zgadza się tożsamość artefaktu T02"):
        db.session.execute(text((DEMO_SCRIPTS / "fixtures.sql").read_text()))
