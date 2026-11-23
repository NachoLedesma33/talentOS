from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.jobs.models import Job, JobRequirement, JobStatus, JobVersion


def get_job(db: DBSession, organization_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    """Devuelve la vacante solo si pertenece a la organización autenticada."""
    stmt = select(Job).where(
        Job.organization_id == organization_id,
        Job.id == job_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_jobs(
    db: DBSession,
    organization_id: uuid.UUID,
    status: JobStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Job]:
    """Lista vacantes del tenant, con filtro opcional por estado y paginación."""
    stmt = select(Job).where(Job.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    stmt = stmt.order_by(Job.created_at, Job.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_jobs(
    db: DBSession, organization_id: uuid.UUID, status: JobStatus | None = None
) -> int:
    """Cuenta las vacantes del tenant con el mismo filtro, sin paginación."""
    stmt = select(func.count()).select_from(Job).where(Job.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    return int(db.scalar(stmt) or 0)


def get_requirement(
    db: DBSession, organization_id: uuid.UUID, requirement_id: uuid.UUID
) -> JobRequirement | None:
    """Devuelve el requisito solo si su vacante pertenece a la organización."""
    stmt = (
        select(JobRequirement)
        .join(Job, Job.id == JobRequirement.job_id)
        .where(
            Job.organization_id == organization_id,
            JobRequirement.id == requirement_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_requirements(
    db: DBSession, organization_id: uuid.UUID, job_id: uuid.UUID
) -> list[JobRequirement]:
    """Lista requisitos de una vacante propia; nunca los de otra organización."""
    stmt = (
        select(JobRequirement)
        .join(Job, Job.id == JobRequirement.job_id)
        .where(
            Job.organization_id == organization_id,
            JobRequirement.job_id == job_id,
        )
        .order_by(JobRequirement.created_at, JobRequirement.id)
    )
    return list(db.execute(stmt).scalars().all())


def get_version(
    db: DBSession, organization_id: uuid.UUID, job_id: uuid.UUID, version: int
) -> JobVersion | None:
    """Devuelve una versión solo si la vacante pertenece a la organización."""
    stmt = (
        select(JobVersion)
        .join(Job, Job.id == JobVersion.job_id)
        .where(
            Job.organization_id == organization_id,
            JobVersion.job_id == job_id,
            JobVersion.version == version,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_versions(
    db: DBSession, organization_id: uuid.UUID, job_id: uuid.UUID
) -> list[JobVersion]:
    """Lista versiones de una vacante propia, ordenadas por número de versión."""
    stmt = (
        select(JobVersion)
        .join(Job, Job.id == JobVersion.job_id)
        .where(
            Job.organization_id == organization_id,
            JobVersion.job_id == job_id,
        )
        .order_by(JobVersion.version)
    )
    return list(db.execute(stmt).scalars().all())
