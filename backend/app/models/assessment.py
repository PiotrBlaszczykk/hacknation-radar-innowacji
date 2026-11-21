from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class Assessment(db.Model):
    """Ocena potencjału. Każde uruchomienie oceny to nowy wiersz, obowiązuje najnowszy."""

    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    innovation_id: Mapped[int] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    criteria_version: Mapped[str] = mapped_column(String(40))
    engine: Mapped[str] = mapped_column(String(120))  # nazwa modelu, "heurystyka" albo "czlowiek"
    total: Mapped[float] = mapped_column(Float)  # 0-100, średnia ważona
    confidence: Mapped[float | None] = mapped_column(Float)  # 0-1
    # Lista: {key, label, weight, score (0-5), confidence, justification, evidence, probabilities}
    items: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    assessor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # gdy ocenia człowiek
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "innovation_id": self.innovation_id,
            "criteria_version": self.criteria_version,
            "engine": self.engine,
            "total": self.total,
            "confidence": self.confidence,
            "items": self.items or [],
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Recommendation(db.Model):
    """Rekomendowana ścieżka dalszego postępowania z innowacją."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    innovation_id: Mapped[int] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(40))  # domain.PATHS
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    # Lista kroków: {title, description, instrument, url}
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    # Po czym poznamy, że rekomendacja zadziałała: {name, target}
    metrics: Mapped[list] = mapped_column(JSONB, default=list)
    engine: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "innovation_id": self.innovation_id,
            "path": self.path,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "steps": self.steps or [],
            "metrics": self.metrics or [],
            "engine": self.engine,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
