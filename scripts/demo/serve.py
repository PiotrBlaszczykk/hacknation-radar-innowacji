"""Lokalne API kopii T14. Uruchamiane przez serve.sh."""

import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL

from app import create_app
from app.extensions import db

cache = Path(os.environ["T14_STATE_DIR"]) / "cache"
app = create_app({
    "SQLALCHEMY_DATABASE_URI": URL.create(
        "postgresql+psycopg", username="radar", password=os.environ.get("PGPASSWORD", "radar"),
        host="127.0.0.1", port=5432, database="radar_t14_demo",
    ).render_as_string(hide_password=False),
    "BASAL_URL": os.environ.get("BASAL_URL", "http://127.0.0.1:8000"),
    "RADON_CACHE_DIR": cache / "radon",
    "INSTITUTIONS_CACHE_DIR": cache / "instytucje",
    "PUBLIC_PROJECTS_CACHE_DIR": cache / "projekty_publiczne",
    "PATENT_CACHE_DIR": cache / "patenty",
})

with app.app_context():
    marker = db.session.scalar(text(
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = current_database()"
    ))
    if marker != "Wihajster T14 demo copy":
        raise SystemExit("Uruchom najpierw scripts/demo/prepare.sh.")

app.run(host="127.0.0.1", port=5014, use_reloader=True)
