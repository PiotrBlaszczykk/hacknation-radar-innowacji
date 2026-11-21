from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..config import EMBED_DIM
from ..extensions import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # domain.ORG_KINDS
    region: Mapped[str | None] = mapped_column(String(80))  # województwo
    city: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(300))
    # Czego organizacja szuka i w czym może pomóc: klucze z domain.DOMAINS.
    interests: Mapped[list] = mapped_column(JSONB, default=list)
    # Identyfikatory w systemach zewnętrznych, np. {"radon": "uuid"}.
    external_ids: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "region": self.region,
            "city": self.city,
            "description": self.description,
            "website": self.website,
            "interests": self.interests or [],
        }


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40))  # domain.USER_ROLES
    title: Mapped[str | None] = mapped_column(String(200))  # stanowisko
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    # Profil do rekomendacji: czego szukam, własnymi słowami, oraz wybrane obszary (domain.DOMAINS).
    about: Mapped[str | None] = mapped_column(Text)
    interests: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    organization: Mapped[Organization | None] = relationship(back_populates="users")

    def embedding_text(self) -> str:
        return "\n".join(p for p in [self.title, self.about] if p)[:6000]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "title": self.title,
            "about": self.about,
            "interests": self.interests or [],
            "organization": self.organization.to_dict() if self.organization else None,
        }
