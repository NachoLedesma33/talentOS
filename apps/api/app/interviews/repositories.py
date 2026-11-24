from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.interviews.models import (
    InterviewFeedback,
    InterviewFeedbackStatus,
    InterviewGuide,
    InterviewGuideRevision,
    InterviewQuestion,
    InterviewQuestionCategory,
    InterviewTenantMismatchError,
)


def get_guide(
    db: DBSession, organization_id: uuid.UUID, guide_id: uuid.UUID
) -> InterviewGuide | None:
    """Lee una guía solo si pertenece a la organización autenticada."""
    stmt = select(InterviewGuide).where(
        InterviewGuide.organization_id == organization_id,
        InterviewGuide.id == guide_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_guides(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[InterviewGuide]:
    """Lista guías del tenant con filtro opcional y paginación."""
    stmt = select(InterviewGuide).where(InterviewGuide.organization_id == organization_id)
    if application_id is not None:
        stmt = stmt.where(InterviewGuide.application_id == application_id)
    stmt = stmt.order_by(InterviewGuide.created_at, InterviewGuide.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def next_version(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> int:
    """Devuelve la siguiente versión disponible para la postulación del tenant."""
    stmt = select(func.coalesce(func.max(InterviewGuide.version), 0)).where(
        InterviewGuide.organization_id == organization_id,
        InterviewGuide.application_id == application_id,
    )
    return int(db.scalar(stmt) or 0) + 1


def save_revision(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    guide_id: uuid.UUID,
    version: int,
    snapshot: dict[str, object],
    created_by: uuid.UUID,
) -> InterviewGuideRevision:
    """Persiste un snapshot saneado; verifica el tenant antes de escribir."""
    safe_snapshot = validate_safe_payload(snapshot)
    guide = db.execute(
        select(InterviewGuide.id).where(
            InterviewGuide.organization_id == organization_id,
            InterviewGuide.id == guide_id,
        )
    ).scalar_one_or_none()
    if guide is None:
        raise InterviewTenantMismatchError("La guía no pertenece a la organización")
    revision = InterviewGuideRevision(
        organization_id=organization_id,
        guide_id=guide_id,
        version=version,
        snapshot=safe_snapshot,
        created_by=created_by,
    )
    db.add(revision)
    db.flush()
    return revision


def get_revision(
    db: DBSession, organization_id: uuid.UUID, guide_id: uuid.UUID, version: int
) -> InterviewGuideRevision | None:
    """Lee una versión concreta del historial dentro del tenant."""
    stmt = select(InterviewGuideRevision).where(
        InterviewGuideRevision.organization_id == organization_id,
        InterviewGuideRevision.guide_id == guide_id,
        InterviewGuideRevision.version == version,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_revisions(
    db: DBSession, organization_id: uuid.UUID, guide_id: uuid.UUID
) -> list[InterviewGuideRevision]:
    """Historial completo de la guía, ordenado por versión dentro del tenant."""
    stmt = (
        select(InterviewGuideRevision)
        .where(
            InterviewGuideRevision.organization_id == organization_id,
            InterviewGuideRevision.guide_id == guide_id,
        )
        .order_by(InterviewGuideRevision.version, InterviewGuideRevision.id)
    )
    return list(db.execute(stmt).scalars().all())


def get_question(
    db: DBSession, organization_id: uuid.UUID, question_id: uuid.UUID
) -> InterviewQuestion | None:
    """Lee una pregunta solo si pertenece a la organización autenticada."""
    stmt = select(InterviewQuestion).where(
        InterviewQuestion.organization_id == organization_id,
        InterviewQuestion.id == question_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_questions(
    db: DBSession,
    organization_id: uuid.UUID,
    guide_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    category: InterviewQuestionCategory | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[InterviewQuestion]:
    """Lista preguntas del tenant; todas las consultas llevan el filtro de organización."""
    stmt = select(InterviewQuestion).where(InterviewQuestion.organization_id == organization_id)
    if guide_id is not None:
        stmt = stmt.where(InterviewQuestion.guide_id == guide_id)
    if requirement_id is not None:
        stmt = stmt.where(InterviewQuestion.requirement_id == requirement_id)
    if category is not None:
        stmt = stmt.where(InterviewQuestion.category == category)
    stmt = stmt.order_by(InterviewQuestion.position, InterviewQuestion.id).limit(limit).offset(
        offset
    )
    return list(db.execute(stmt).scalars().all())


def get_feedback(
    db: DBSession, organization_id: uuid.UUID, feedback_id: uuid.UUID
) -> InterviewFeedback | None:
    """Lee un registro humano solo si pertenece a la organización autenticada."""
    stmt = select(InterviewFeedback).where(
        InterviewFeedback.organization_id == organization_id,
        InterviewFeedback.id == feedback_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_feedback(
    db: DBSession,
    organization_id: uuid.UUID,
    question_id: uuid.UUID | None = None,
    guide_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
    status: InterviewFeedbackStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[InterviewFeedback]:
    """Lista feedback del tenant con filtros y paginación; sin lógica de negocio."""
    stmt = select(InterviewFeedback).where(InterviewFeedback.organization_id == organization_id)
    if question_id is not None:
        stmt = stmt.where(InterviewFeedback.question_id == question_id)
    if guide_id is not None:
        stmt = stmt.where(InterviewFeedback.guide_id == guide_id)
    if application_id is not None:
        stmt = stmt.where(InterviewFeedback.application_id == application_id)
    if status is not None:
        stmt = stmt.where(InterviewFeedback.status == status)
    stmt = stmt.order_by(InterviewFeedback.created_at, InterviewFeedback.id).limit(limit).offset(
        offset
    )
    return list(db.execute(stmt).scalars().all())
