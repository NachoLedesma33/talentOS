from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)


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


def get_assessment_evaluation(
    db: DBSession,
    organization_id: uuid.UUID,
    assessment_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> RequirementEvaluation | None:
    """Lee un criterio solo si pertenece a la evaluación y al tenant indicados."""
    stmt = (
        select(RequirementEvaluation)
        .join(Assessment, Assessment.id == RequirementEvaluation.assessment_id)
        .where(
            Assessment.organization_id == organization_id,
            Assessment.id == assessment_id,
            RequirementEvaluation.id == evaluation_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_assessment_evaluations(
    db: DBSession, organization_id: uuid.UUID, assessment_id: uuid.UUID
) -> list[RequirementEvaluation]:
    """Todos los criterios de una evaluación del tenant, sin límite arbitrario."""
    stmt = (
        select(RequirementEvaluation)
        .join(Assessment, Assessment.id == RequirementEvaluation.assessment_id)
        .where(
            Assessment.organization_id == organization_id,
            RequirementEvaluation.assessment_id == assessment_id,
        )
        .order_by(RequirementEvaluation.requirement_id, RequirementEvaluation.id)
    )
    return list(db.execute(stmt).scalars().all())


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


def create_assessment(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    job_version_id: uuid.UUID,
    candidate_id: uuid.UUID,
    created_by: uuid.UUID,
    model_version: str,
    prompt_version: str,
) -> Assessment:
    """Inserta la evaluación; autorización, versión e idempotencia son del servicio."""
    assessment = Assessment(
        organization_id=organization_id,
        application_id=application_id,
        job_version_id=job_version_id,
        candidate_id=candidate_id,
        created_by=created_by,
        model_version=model_version,
        prompt_version=prompt_version,
    )
    db.add(assessment)
    db.flush()
    return assessment


def save_evaluation(
    db: DBSession,
    *,
    assessment_id: uuid.UUID,
    requirement_id: uuid.UUID,
    status: RequirementEvaluationStatus,
    explanation: str,
    evidence: list[dict[str, object]],
    limitations: list[str],
    review_required: bool,
) -> RequirementEvaluation:
    """Persiste un criterio ya validado; sin reglas de negocio ni commit."""
    evaluation = RequirementEvaluation(
        assessment_id=assessment_id,
        requirement_id=requirement_id,
        status=status,
        explanation=explanation,
        evidence=evidence,
        limitations=limitations,
        review_required=review_required,
    )
    db.add(evaluation)
    db.flush()
    return evaluation


def update_summary(
    db: DBSession,
    assessment: Assessment,
    *,
    status: AssessmentStatus,
    summary: dict[str, object],
    limitations: list[str],
) -> Assessment:
    """Actualiza resumen y estado calculados por el servicio; sin commit."""
    assessment.status = status
    assessment.summary = summary
    assessment.limitations = limitations
    db.flush()
    return assessment


def update_evaluation_review(
    db: DBSession,
    evaluation: RequirementEvaluation,
    *,
    status: RequirementEvaluationStatus,
    explanation: str | None,
    reviewed_by: uuid.UUID,
    reviewed_at: datetime,
    review_required: bool,
) -> RequirementEvaluation:
    """Persiste la decisión humana; el servicio valida permisos y commit."""
    evaluation.status = status
    if explanation is not None:
        evaluation.explanation = explanation
    evaluation.reviewed_by = reviewed_by
    evaluation.reviewed_at = reviewed_at
    evaluation.review_required = review_required
    db.flush()
    return evaluation
