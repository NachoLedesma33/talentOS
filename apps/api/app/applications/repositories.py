from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.applications.models import Application, ApplicationStage, StageChange


def get_application(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> Application | None:
    """Devuelve la postulación solo si pertenece a la organización autenticada."""
    stmt = select(Application).where(
        Application.organization_id == organization_id,
        Application.id == application_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_applications(
    db: DBSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    stage: ApplicationStage | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Application]:
    """Lista postulaciones del tenant con filtros opcionales y paginación."""
    stmt = select(Application).where(Application.organization_id == organization_id)
    if job_id is not None:
        stmt = stmt.where(Application.job_id == job_id)
    if candidate_id is not None:
        stmt = stmt.where(Application.candidate_id == candidate_id)
    if stage is not None:
        stmt = stmt.where(Application.stage == stage)
    stmt = stmt.order_by(Application.created_at, Application.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_applications(
    db: DBSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    stage: ApplicationStage | None = None,
) -> int:
    """Cuenta las postulaciones del tenant con los mismos filtros, sin paginar."""
    stmt = select(func.count()).select_from(Application).where(
        Application.organization_id == organization_id
    )
    if job_id is not None:
        stmt = stmt.where(Application.job_id == job_id)
    if candidate_id is not None:
        stmt = stmt.where(Application.candidate_id == candidate_id)
    if stage is not None:
        stmt = stmt.where(Application.stage == stage)
    return int(db.scalar(stmt) or 0)


def list_stage_changes(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> list[StageChange]:
    """Lee el historial de una postulación propia; nunca el de otro tenant."""
    stmt = (
        select(StageChange)
        .join(Application, Application.id == StageChange.application_id)
        .where(
            Application.organization_id == organization_id,
            StageChange.application_id == application_id,
        )
        .order_by(StageChange.created_at, StageChange.id)
    )
    return list(db.execute(stmt).scalars().all())
