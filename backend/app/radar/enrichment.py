from collections.abc import Callable, Iterator

from sqlalchemy import select

from .. import domain
from ..extensions import db
from ..models import Event, Innovation
from ..services import embeddings

TEXT_FIELDS = ("summary", "problem", "solution", "results")
CHOICE_FIELDS = {"kind": domain.INNOVATION_KINDS, "stage": domain.STAGES}
LIST_FIELDS = {"domains": domain.DOMAINS, "support_needs": domain.SUPPORT_NEEDS, "keywords": None}
GENERATED_FIELDS = (*TEXT_FIELDS, *CHOICE_FIELDS, *LIST_FIELDS)


def apply_structure(innovation: Innovation, result: dict) -> None:
    card = result["card"]
    engine = result["engine"]
    engine_name = (
        " + ".join(dict.fromkeys(engine[key] for key in ("tags", "text") if engine.get(key)))
        if isinstance(engine, dict) else engine
    )
    raw = innovation.raw or {}
    protected = set(raw.get("manual_fields", []))
    if raw.get("evidence") or (innovation.results and not raw.get("structuring_version")):
        protected.add("results")

    values = {name: card.get(name) or None for name in TEXT_FIELDS}
    values.update({name: card.get(name) if card.get(name) in options else None for name, options in CHOICE_FIELDS.items()})
    values.update({
        name: list(dict.fromkeys(key for key in (card.get(name) or []) if options is None or key in options))
        for name, options in LIST_FIELDS.items()
    })
    for name, value in values.items():
        if name not in protected and (value or not getattr(innovation, name) or raw.get("structuring_version")):
            setattr(innovation, name, value)

    innovation.structured_by = engine_name[:120]
    innovation.raw = {
        **raw, "is_innovation": result["is_innovation"], "structuring_version": result.get("version"),
        "structuring_engine": engine, "structured_title": card.get("title"),
        "structuring_questions": result.get("questions", []),
    }
    db.session.add(Event(
        innovation_id=innovation.id, type="ustrukturyzowana",
        message="Model uzupełnił propozycję karty wykrytej innowacji.",
        payload={"version": result.get("version"), "engine": engine},
    ))


def enrich(limit: int, structure_text: Callable[[str], dict]) -> Iterator[int]:
    for _ in range(limit):
        innovation = db.session.scalar(
            select(Innovation)
            .where(
                Innovation.origin == "radar", Innovation.structured_by.is_(None),
                Innovation.status != "archiwum", Innovation.claimed.is_(False),
            )
            .order_by(Innovation.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if innovation is None:
            db.session.rollback()
            return
        apply_structure(innovation, structure_text(f"{innovation.title}\n\n{innovation.description or ''}"))
        embeddings.try_embed(innovation)
        innovation_id = innovation.id
        db.session.commit()
        yield innovation_id
