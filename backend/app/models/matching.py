from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..config import EMBED_DIM
from ..extensions import db
from .innovation import Innovation
from .org import Organization, User


class Need(db.Model):
    """Zapotrzebowanie: organizacja opisuje problem, dla którego szuka rozwiązania."""

    __tablename__ = "needs"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(400))
    description: Mapped[str | None] = mapped_column(Text)
    domains: Mapped[list] = mapped_column(JSONB, default=list)
    # Co organizacja może dać: klucze domain.SUPPORT_NEEDS (np. finansowanie, pierwszy_uzytkownik).
    offers: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="otwarte")  # otwarte | zamkniete
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    organization: Mapped[Organization] = relationship()
    author: Mapped[User | None] = relationship()

    def embedding_text(self) -> str:
        return "\n".join(p for p in [self.title, self.description] if p)[:6000]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "domains": self.domains or [],
            "offers": self.offers or [],
            "status": self.status,
            "organization": self.organization.to_dict(),
            "author": {"id": self.author.id, "name": self.author.name} if self.author else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Match(db.Model):
    """Dopasowanie innowacji do zapotrzebowania albo do organizacji (partner, inwestor)."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    innovation_id: Mapped[int] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[int | None] = mapped_column(ForeignKey("needs.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str | None] = mapped_column(String(40))  # uzytkownik | partner | inwestor
    score: Mapped[float] = mapped_column(Float)  # 0-1
    reason: Mapped[str | None] = mapped_column(Text)
    # Składniki wyniku, żeby dało się go wyjaśnić: {similarity, domains, offers, ...}
    factors: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="proponowane")  # domain.MATCH_STATUSES
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    innovation: Mapped[Innovation] = relationship()
    need: Mapped[Need | None] = relationship()
    organization: Mapped[Organization | None] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "innovation_id": self.innovation_id,
            "need": self.need.to_dict() if self.need else None,
            "organization": self.organization.to_dict() if self.organization else None,
            "role": self.role,
            "score": self.score,
            "reason": self.reason,
            "factors": self.factors or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Interaction(db.Model):
    """Warstwa społecznościowa: obserwowanie, zainteresowanie, komentarz, prośba o kontakt."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    innovation_id: Mapped[int] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))  # obserwuje | zainteresowany | komentarz | kontakt
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[User] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "body": self.body,
            "user": self.user.to_dict(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
