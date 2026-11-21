from collections.abc import Callable, Iterator

from sqlalchemy import select

from .. import domain
from ..extensions import db
from ..models import Event, Innovation
from ..services import embeddings


def enrich(limit: int, structure_text: Callable[[str], dict]) -> Iterator[int]:
    for _ in range(limit):
        innovation = db.session.scalar(
            select(Innovation)
            .where(Innovation.origin == "radar", Innovation.structured_by.is_(None))
            .order_by(Innovation.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if innovation is None:
            db.session.rollback()
            return
        result = structure_text(f"{innovation.title}\n\n{innovation.description or ''}")
        card = result["card"]
        engine = result["engine"]
        innovation.structured_by = (
            " + ".join(dict.fromkeys(engine[key] for key in ("tags", "text") if engine.get(key)))
            if isinstance(engine, dict) else engine
        )[:120]
        if card.get("summary"):
            innovation.summary = card["summary"]
        innovation.problem = card.get("problem")
        innovation.solution = card.get("solution")
        innovation.kind = card.get("kind") if card.get("kind") in domain.INNOVATION_KINDS else None
        innovation.stage = card.get("stage") if card.get("stage") in domain.STAGES else None
        innovation.domains = list(dict.fromkeys(key for key in (card.get("domains") or []) if key in domain.DOMAINS))
        innovation.raw = {**(innovation.raw or {}), "is_innovation": result["is_innovation"]}
        innovation.events.append(
            Event(type="ustrukturyzowana", message="Model uzupełnił propozycję karty wykrytej innowacji.")
        )
        embeddings.try_embed(innovation)
        innovation_id = innovation.id
        db.session.commit()
        yield innovation_id
