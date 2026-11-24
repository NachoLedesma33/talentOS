from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.assessment.models import Assessment, RequirementEvaluation


def get_assessment(
    db: DBSession, organization_id: uuid.UUID, assessment_id: uuid.UUID
) -> Assessment | None:
    """Devuelve la evaluación solo si pertenece a la organización autenticada."""
    stmt = select(Assessment).where(
        Assessment.organization_id == organization_id,
        Assessment.id == assessment_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_assessments(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Assessment]:
    """Lista evaluaciones del tenant con filtros opcionales y paginación."""
    stmt = select(Assessment).where(Assessment.organization_id == organization_id)
    if application_id is not None:
        stmt = stmt.where(Assessment.application_id == application_id)
    if candidate_id is not None:
        stmt = stmt.where(Assessment.candidate_id == candidate_id)
    stmt = stmt.order_by(Assessment.created_at, Assessment.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_assessments(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
) -> int:
    """Cuenta las evaluaciones del tenant con los mismos filtros, sin paginar."""
    stmt = select(func.count()).select_from(Assessment).where(
        Assessment.organization_id == organization_id
    )
    if application_id is not None:
        stmt = stmt.where(Assessment.application_id == application_id)
    if candidate_id is not None:
        stmt = stmt.where(Assessment.candidate_id == candidate_id)
    return int(db.scalar(stmt) or 0)


def get_evaluation(
    db: DBSession, organization_id: uuid.UUID, evaluation_id: uuid.UUID
) -> RequirementEvaluation | None:
    """Lee un criterio solo si su evaluación pertenece al tenant autenticado."""
    stmt = (
        select(RequirementEvaluation)
        .join(Assessment, Assessment.id == RequirementEvaluation.assessment_id)
        .where(
            Assessment.organization_id == organization_id,
            RequirementEvaluation.id == evaluation_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_evaluations(
    db: DBSession,
    organization_id: uuid.UUID,
    assessment_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RequirementEvaluation]:
    """Lista criterios del tenant; el tenant se resuelve por la evaluación padre."""
    stmt = (
        select(RequirementEvaluation)
        .join(Assessment, Assessment.id == RequirementEvaluation.assessment_id)
        .where(Assessment.organization_id == organization_id)
    )
    if assessment_id is not None:
        stmt = stmt.where(RequirementEvaluation.assessment_id == assessment_id)
    if requirement_id is not None:
        stmt = stmt.where(RequirementEvaluation.requirement_id == requirement_id)
    stmt = stmt.order_by(RequirementEvaluation.created_at, RequirementEvaluation.id)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())
