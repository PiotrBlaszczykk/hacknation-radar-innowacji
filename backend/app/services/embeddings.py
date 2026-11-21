"""Embeddingi i wyszukiwanie najbliższych sąsiadów (pgvector, odległość kosinusowa).

Działa dla każdego modelu, który ma kolumnę `embedding` i metodę `embedding_text()`.
"""

from sqlalchemy import select

from ..extensions import db
from . import llm


def try_embed(obj) -> bool:
    """Liczy embedding obiektu. Gdy model jest niedostępny, zostawia NULL (dogoni to `flask embed`)."""
    try:
        obj.embedding = llm.embed([obj.embedding_text()])[0]
        return True
    except llm.LLMUnavailable:
        return False


def embed_missing(model, batch: int = 16) -> int:
    done = 0
    while True:
        rows = db.session.scalars(select(model).where(model.embedding.is_(None)).limit(batch)).all()
        if not rows:
            return done
        vectors = llm.embed([row.embedding_text() for row in rows])
        for row, vector in zip(rows, vectors):
            row.embedding = vector
        db.session.commit()
        done += len(rows)


def nearest(model, vector, *, limit: int = 10, exclude_id: int | None = None, where=None) -> list[tuple]:
    """Zwraca listę (obiekt, podobieństwo 0-1), od najbardziej podobnego."""
    distance = model.embedding.cosine_distance(vector)
    query = select(model, (1 - distance).label("similarity")).where(model.embedding.is_not(None))
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if where is not None:
        query = query.where(where)
    rows = db.session.execute(query.order_by(distance).limit(limit)).all()
    return [(row[0], float(row[1])) for row in rows]
