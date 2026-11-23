from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    """Timestamp UTC aplicado por Python; la BD no define defaults de reloj local."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class CandidateProfileStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"


class Candidate(Base):
    """Datos profesionales mínimos; sin atributos protegidos ni inferencias sensibles."""

    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    profile_status: Mapped[CandidateProfileStatus] = mapped_column(
        SAEnum(
            CandidateProfileStatus,
            name="profile_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=CandidateProfileStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_candidates_profile_status", "profile_status"),
        # Email no único: RF-027 (duplicados) es P1 y se tratará en su unidad.
        Index("ix_candidates_email", "email"),
    )


class CandidateNote(Base):
    """Nota interna con autor identificable; acceso restringido por rol."""

    __tablename__ = "candidate_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
