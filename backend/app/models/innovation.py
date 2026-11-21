from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..config import EMBED_DIM
from ..extensions import db
from .org import Organization, User


class Innovation(db.Model):
    __tablename__ = "innovations"
    __table_args__ = (UniqueConstraint("source_name", "source_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # Karta innowacji
    title: Mapped[str] = mapped_column(String(400))
    summary: Mapped[str | None] = mapped_column(Text)  # 1-2 zdania do feedu
    description: Mapped[str | None] = mapped_column(Text)  # pełny tekst od twórcy lub ze źródła
    problem: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    results: Mapped[str | None] = mapped_column(Text)  # dowody, liczby, efekty
    kind: Mapped[str | None] = mapped_column(String(40), index=True)  # domain.INNOVATION_KINDS
    stage: Mapped[str | None] = mapped_column(String(40), index=True)  # domain.STAGES
    domains: Mapped[list] = mapped_column(JSONB, default=list)  # klucze domain.DOMAINS
    support_needs: Mapped[list] = mapped_column(JSONB, default=list)  # klucze domain.SUPPORT_NEEDS
    keywords: Mapped[list] = mapped_column(JSONB, default=list)

    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # Pochodzenie
    origin: Mapped[str] = mapped_column(String(20), default="zgloszenie", index=True)  # domain.ORIGINS
    source_name: Mapped[str | None] = mapped_column(String(80))  # np. "radon_projekty"
    source_ref: Mapped[str | None] = mapped_column(String(200))  # id w źródle
    source_url: Mapped[str | None] = mapped_column(String(500))
    # False = profil utworzony przez radar, którego twórca jeszcze nie potwierdził.
    claimed: Mapped[bool] = mapped_column(default=True)
    # Kto wypełnił kartę: "czlowiek" albo nazwa modelu.
    structured_by: Mapped[str | None] = mapped_column(String(120))
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)  # oryginalny rekord ze źródła

    status: Mapped[str] = mapped_column(String(20), default="zgloszona", index=True)  # domain.STATUSES

    # Kopie z najnowszej oceny i rekomendacji, żeby dało się po nich sortować i filtrować listę.
    score: Mapped[float | None] = mapped_column(Float, index=True)  # 0-100
    path: Mapped[str | None] = mapped_column(String(40))  # domain.PATHS
    # Świeżość wobec tego, co już jest w systemie: 0 = istnieje niemal to samo, 100 = nic podobnego.
    novelty: Mapped[float | None] = mapped_column(Float)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    organization: Mapped[Organization | None] = relationship()
    author: Mapped[User | None] = relationship()
    events: Mapped[list["Event"]] = relationship(
        back_populates="innovation", order_by="Event.created_at", cascade="all, delete-orphan"
    )

    def embedding_text(self) -> str:
        parts = [self.title, self.summary, self.problem, self.solution, self.description]
        return "\n".join(p for p in parts if p)[:6000]

    def to_dict(self, full: bool = False) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "kind": self.kind,
            "stage": self.stage,
            "domains": self.domains or [],
            "support_needs": self.support_needs or [],
            "keywords": self.keywords or [],
            "origin": self.origin,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "claimed": self.claimed,
            "status": self.status,
            "score": self.score,
            "path": self.path,
            "novelty": self.novelty,
            "organization": self.organization.to_dict() if self.organization else None,
            "author": {"id": self.author.id, "name": self.author.name, "title": self.author.title}
            if self.author
            else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if full:
            data.update(
                description=self.description,
                problem=self.problem,
                solution=self.solution,
                results=self.results,
                structured_by=self.structured_by,
                events=[e.to_dict() for e in self.events],
            )
        return data


class Event(db.Model):
    """Historia innowacji: co i kiedy się z nią działo (także ślad audytowy)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    innovation_id: Mapped[int] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))  # np. wykryta, zgloszona, oceniona, status
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # None = system
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    innovation: Mapped[Innovation] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "message": self.message,
            "payload": self.payload or {},
            "actor": self.actor.name if self.actor else "Radar",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
