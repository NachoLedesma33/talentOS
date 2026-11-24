from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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


class InterviewDomainError(ValueError):
    """Error determinista del dominio de entrevistas; sin datos personales."""


class InvalidInterviewTransitionError(InterviewDomainError):
    """Transición de estado no permitida por el contrato de entrevista."""


class InterviewTenantMismatchError(InterviewDomainError):
    """El contexto de organización no coincide con el recurso solicitado."""


class InterviewGuideStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class InterviewQuestionCategory(StrEnum):
    TECHNICAL = "technical"
    DEEP_DIVE = "deep_dive"


class InterviewQuestionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class InterviewFeedbackStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    NEEDS_REVIEW = "needs_review"


GUIDE_TRANSITIONS: dict[InterviewGuideStatus, frozenset[InterviewGuideStatus]] = {
    InterviewGuideStatus.DRAFT: frozenset(
        {InterviewGuideStatus.PUBLISHED, InterviewGuideStatus.ARCHIVED}
    ),
    InterviewGuideStatus.PUBLISHED: frozenset({InterviewGuideStatus.ARCHIVED}),
    InterviewGuideStatus.ARCHIVED: frozenset(),
}

QUESTION_TRANSITIONS: dict[InterviewQuestionStatus, frozenset[InterviewQuestionStatus]] = {
    InterviewQuestionStatus.DRAFT: frozenset(
        {
            InterviewQuestionStatus.APPROVED,
            InterviewQuestionStatus.REJECTED,
            InterviewQuestionStatus.ARCHIVED,
        }
    ),
    InterviewQuestionStatus.REJECTED: frozenset({InterviewQuestionStatus.DRAFT}),
    InterviewQuestionStatus.APPROVED: frozenset({InterviewQuestionStatus.ARCHIVED}),
    InterviewQuestionStatus.ARCHIVED: frozenset(),
}

FEEDBACK_TRANSITIONS: dict[InterviewFeedbackStatus, frozenset[InterviewFeedbackStatus]] = {
    InterviewFeedbackStatus.PENDING: frozenset(
        {InterviewFeedbackStatus.SUBMITTED, InterviewFeedbackStatus.NEEDS_REVIEW}
    ),
    InterviewFeedbackStatus.NEEDS_REVIEW: frozenset({InterviewFeedbackStatus.SUBMITTED}),
    InterviewFeedbackStatus.SUBMITTED: frozenset(),
}


def _utcnow() -> datetime:
    """Timestamp UTC aplicado por Python; la BD no define reloj local."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


def ensure_guide_transition(
    current: InterviewGuideStatus, target: InterviewGuideStatus
) -> None:
    if target not in GUIDE_TRANSITIONS.get(current, frozenset()):
        raise InvalidInterviewTransitionError(
            f"Transición de guía no permitida: {current} -> {target}"
        )


def ensure_question_transition(
    current: InterviewQuestionStatus, target: InterviewQuestionStatus
) -> None:
    if target not in QUESTION_TRANSITIONS.get(current, frozenset()):
        raise InvalidInterviewTransitionError(
            f"Transición de pregunta no permitida: {current} -> {target}"
        )


def ensure_feedback_transition(
    current: InterviewFeedbackStatus, target: InterviewFeedbackStatus
) -> None:
    if target not in FEEDBACK_TRANSITIONS.get(current, frozenset()):
        raise InvalidInterviewTransitionError(
            f"Transición de feedback no permitida: {current} -> {target}"
        )


class InterviewGuide(Base):
    """Guía versionada por postulación; estados del SDD, sin decisiones de contratación."""

    __tablename__ = "interview_guides"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[InterviewGuideStatus] = mapped_column(
        SAEnum(
            InterviewGuideStatus,
            name="interview_guide_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=InterviewGuideStatus.DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
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
            "version",
            name="uq_interview_guides_org_app_version",
        ),
        CheckConstraint("version >= 1", name="ck_interview_guides_version_positive"),
        Index("ix_interview_guides_organization_id", "organization_id"),
        Index("ix_interview_guides_application_id", "application_id"),
        Index("ix_interview_guides_status", "status"),
    )

    def transition_to(self, target: InterviewGuideStatus) -> InterviewGuide:
        ensure_guide_transition(self.status, target)
        self.status = target
        return self


class InterviewGuideRevision(Base):
    """Snapshot saneado de cada versión de guía; permite consultar el historial."""

    __tablename__ = "interview_guide_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_guides.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("guide_id", "version", name="uq_interview_guide_revisions_guide_version"),
        CheckConstraint("version >= 1", name="ck_interview_guide_revisions_version_positive"),
        Index("ix_interview_guide_revisions_organization_id", "organization_id"),
        Index("ix_interview_guide_revisions_guide_id", "guide_id"),
    )


class InterviewQuestion(Base):
    """Pregunta por requisito inmutable; sin atributos protegidos ni puntaje."""

    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_guides.id", ondelete="CASCADE"), nullable=False
    )
    # Referencia lógica al snapshot inmutable de JobVersion; no FK a tabla mutable.
    requirement_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[InterviewQuestionCategory] = mapped_column(
        SAEnum(
            InterviewQuestionCategory,
            name="interview_question_category",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_focus: Mapped[str] = mapped_column(String(1000), nullable=False)
    competency: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[InterviewQuestionStatus] = mapped_column(
        SAEnum(
            InterviewQuestionStatus,
            name="interview_question_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=InterviewQuestionStatus.DRAFT,
    )
    review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
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
        UniqueConstraint("guide_id", "position", name="uq_interview_questions_guide_position"),
        UniqueConstraint(
            "guide_id",
            "requirement_id",
            "category",
            name="uq_interview_questions_guide_requirement_category",
        ),
        CheckConstraint("position > 0", name="ck_interview_questions_position_positive"),
        CheckConstraint("length(question) <= 2000", name="ck_interview_questions_question_length"),
        Index("ix_interview_questions_organization_id", "organization_id"),
        Index("ix_interview_questions_guide_id", "guide_id"),
        Index("ix_interview_questions_requirement_id", "requirement_id"),
        Index("ix_interview_questions_status", "status"),
    )

    def transition_to(self, target: InterviewQuestionStatus) -> InterviewQuestion:
        ensure_question_transition(self.status, target)
        self.status = target
        return self


class InterviewFeedback(Base):
    """Evidencia observada por el entrevistador; nunca score ni decisión de contratación."""

    __tablename__ = "interview_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("interview_guides.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    interviewer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[InterviewFeedbackStatus] = mapped_column(
        SAEnum(
            InterviewFeedbackStatus,
            name="interview_feedback_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=InterviewFeedbackStatus.PENDING,
    )
    observed_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    gaps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    follow_up_needed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint("length(notes) <= 1000", name="ck_interview_feedbacks_notes_length"),
        Index("ix_interview_feedbacks_organization_id", "organization_id"),
        Index("ix_interview_feedbacks_question_id", "question_id"),
        Index("ix_interview_feedbacks_guide_id", "guide_id"),
        Index("ix_interview_feedbacks_application_id", "application_id"),
        Index("ix_interview_feedbacks_status", "status"),
    )

    def transition_to(
        self, target: InterviewFeedbackStatus, submitted_at: datetime | None = None
    ) -> InterviewFeedback:
        ensure_feedback_transition(self.status, target)
        if target is InterviewFeedbackStatus.SUBMITTED and submitted_at is None:
            raise InvalidInterviewTransitionError("Envío requiere submitted_at")
        if target is InterviewFeedbackStatus.SUBMITTED:
            self.submitted_at = submitted_at
        self.status = target
        return self
