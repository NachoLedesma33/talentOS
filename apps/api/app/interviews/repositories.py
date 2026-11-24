from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.interviews.models import (
    InterviewFeedback,
    InterviewFeedbackStatus,
    InterviewGuide,
    InterviewGuideRevision,
    InterviewGuideStatus,
    InterviewQuestion,
    InterviewQuestionCategory,
    InterviewTenantMismatchError,
)
from app.jobs.models import Job, JobVersion


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
    status: InterviewGuideStatus | None = None,
) -> list[InterviewGuide]:
    """Lista guías del tenant con filtros opcionales y paginación."""
    stmt = select(InterviewGuide).where(InterviewGuide.organization_id == organization_id)
    if application_id is not None:
        stmt = stmt.where(InterviewGuide.application_id == application_id)
    if status is not None:
        stmt = stmt.where(InterviewGuide.status == status)
    stmt = stmt.order_by(InterviewGuide.created_at, InterviewGuide.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_guides(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
    status: InterviewGuideStatus | None = None,
) -> int:
    """Cuenta solo las guías del tenant con los mismos filtros del listado."""
    filters = [InterviewGuide.organization_id == organization_id]
    if application_id is not None:
        filters.append(InterviewGuide.application_id == application_id)
    if status is not None:
        filters.append(InterviewGuide.status == status)
    return int(db.scalar(select(func.count()).select_from(InterviewGuide).where(*filters)) or 0)


def next_version(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> int:
    """Devuelve la siguiente versión disponible para la postulación del tenant."""
    stmt = select(func.coalesce(func.max(InterviewGuide.version), 0)).where(
        InterviewGuide.organization_id == organization_id,
        InterviewGuide.application_id == application_id,
    )
    return int(db.scalar(stmt) or 0) + 1


def allowed_requirement_ids(
    db: DBSession, organization_id: uuid.UUID, job_version_id: uuid.UUID
) -> frozenset[uuid.UUID]:
    """Requisitos del snapshot inmutable de una versión verificada del tenant."""
    version = db.get(JobVersion, job_version_id)
    if version is None:
        return frozenset()
    job = db.get(Job, version.job_id)
    if job is None or job.organization_id != organization_id:
        return frozenset()
    snapshot_job = version.snapshot.get("job")
    if isinstance(snapshot_job, Mapping):
        snapshot_org = cast(Mapping[str, object], snapshot_job).get("organization_id")
        if snapshot_org is not None and snapshot_org != str(organization_id):
            return frozenset()
    raw_requirements = version.snapshot.get("requirements")
    if not isinstance(raw_requirements, (list, tuple)):
        return frozenset()
    allowed: set[uuid.UUID] = set()
    for item in raw_requirements:
        if not isinstance(item, Mapping):
            continue
        raw_id = cast(Mapping[str, object], item).get("id")
        if not isinstance(raw_id, str):
            continue
        try:
            allowed.add(uuid.UUID(raw_id))
        except ValueError:
            continue
    return frozenset(allowed)


def get_guide_for_generation(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    *,
    job_version_id: uuid.UUID,
    prompt_version: str,
) -> InterviewGuide | None:
    """Busca la guía ya generada para versión de vacante y prompt del tenant."""
    stmt = (
        select(InterviewGuide)
        .join(
            InterviewGuideRevision,
            (InterviewGuideRevision.guide_id == InterviewGuide.id)
            & (InterviewGuideRevision.version == InterviewGuide.version)
            & (InterviewGuideRevision.organization_id == organization_id),
        )
        .where(
            InterviewGuide.organization_id == organization_id,
            InterviewGuide.application_id == application_id,
            InterviewGuideRevision.snapshot["job_version_id"].as_string()
            == str(job_version_id),
            InterviewGuideRevision.snapshot["prompt_version"].as_string() == prompt_version,
        )
        .order_by(InterviewGuide.version)
    )
    return db.execute(stmt).scalar_one_or_none()


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
    db: DBSession,
    organization_id: uuid.UUID,
    guide_id: uuid.UUID,
    limit: int | None = None,
    offset: int = 0,
) -> list[InterviewGuideRevision]:
    """Historial de la guía, ordenado por versión dentro del tenant."""
    stmt = (
        select(InterviewGuideRevision)
        .where(
            InterviewGuideRevision.organization_id == organization_id,
            InterviewGuideRevision.guide_id == guide_id,
        )
        .order_by(InterviewGuideRevision.version, InterviewGuideRevision.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_revisions(
    db: DBSession, organization_id: uuid.UUID, guide_id: uuid.UUID
) -> int:
    """Cuenta las revisiones visibles al tenant para una guía concreta."""
    stmt = select(func.count()).select_from(InterviewGuideRevision).where(
        InterviewGuideRevision.organization_id == organization_id,
        InterviewGuideRevision.guide_id == guide_id,
    )
    return int(db.scalar(stmt) or 0)


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


def count_feedback(
    db: DBSession,
    organization_id: uuid.UUID,
    question_id: uuid.UUID | None = None,
) -> int:
    """Cuenta el feedback del tenant para una pregunta; sin exponer otras orgs."""
    filters = [InterviewFeedback.organization_id == organization_id]
    if question_id is not None:
        filters.append(InterviewFeedback.question_id == question_id)
    stmt = select(func.count()).select_from(InterviewFeedback).where(*filters)
    return int(db.scalar(stmt) or 0)
