from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    """Timestamp UTC aplicado por Python; la BD no define reloj local."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


def _empty_summary() -> dict[str, object]:
    return {"strengths": [], "gaps": [], "questions": []}


class AssessmentStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class RequirementEvaluationStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    NEEDS_REVIEW = "needs_review"


class Assessment(Base):
    """Evaluación de una versión inmutable de vacante; sin score ni atributos protegidos."""

    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("job_versions.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AssessmentStatus] = mapped_column(
        SAEnum(
            AssessmentStatus,
            name="assessment_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=AssessmentStatus.PENDING,
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=_empty_summary
    )
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "application_id",
            "job_version_id",
            "prompt_version",
            name="uq_assessments_org_app_version_prompt",
        ),
        Index("ix_assessments_organization_id", "organization_id"),
        Index("ix_assessments_application_id", "application_id"),
        Index("ix_assessments_candidate_id", "candidate_id"),
        Index("ix_assessments_status", "status"),
    )


class RequirementEvaluation(Base):
    """Resultado por requisito: evidencia acotada, limitaciones y revisión humana."""

    __tablename__ = "requirement_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    # Referencia lógica al requisito del snapshot inmutable de JobVersion; no FK a tabla mutable.
    requirement_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[RequirementEvaluationStatus] = mapped_column(
        SAEnum(
            RequirementEvaluationStatus,
            name="requirement_evaluation_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=RequirementEvaluationStatus.NEEDS_REVIEW,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_requirement_evaluations_assessment_id", "assessment_id"),
        Index("ix_requirement_evaluations_requirement_id", "requirement_id"),
        Index("ix_requirement_evaluations_status", "status"),
    )
