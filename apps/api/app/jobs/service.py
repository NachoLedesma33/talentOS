from __future__ import annotations

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.audit.service import record_audit
from app.identity.repositories import user_belongs_to_organization
from app.jobs.models import (
    Job,
    JobRequirement,
    JobStatus,
    JobVersion,
    RequirementCategory,
    RequirementImportance,
)
from app.jobs.repositories import (
    count_jobs,
    get_requirement,
    list_requirements,
)
from app.jobs.repositories import (
    get_job as get_job_row,
)
from app.jobs.repositories import (
    list_jobs as list_job_rows,
)
from app.jobs.repositories import (
    list_versions as list_job_versions,
)


class JobsDomainError(Exception):
    """Error determinista del dominio de vacantes."""


class JobValidationError(JobsDomainError):
    """Dato de entrada inválido según las reglas del dominio."""


class JobNotFoundError(JobsDomainError):
    """La vacante no existe en la organización autenticada."""


class OwnerNotMemberError(JobsDomainError):
    """El responsable propuesto no pertenece a la organización."""


class InvalidJobStatusTransitionError(JobsDomainError):
    """La transición de estado solicitada no está permitida."""


class JobVersionConflictError(JobsDomainError):
    """El número de versión ya existe para la vacante."""


_ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.DRAFT: frozenset({JobStatus.OPEN}),
    JobStatus.OPEN: frozenset({JobStatus.PAUSED, JobStatus.CLOSED}),
    JobStatus.PAUSED: frozenset({JobStatus.OPEN, JobStatus.CLOSED}),
    JobStatus.CLOSED: frozenset({JobStatus.ARCHIVED}),
    JobStatus.ARCHIVED: frozenset(),
}


def _require_job(db: DBSession, organization_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = get_job_row(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError
    return job


def _require_organization_owner(
    db: DBSession, organization_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    if not user_belongs_to_organization(db, owner_id, organization_id):
        raise OwnerNotMemberError


def get_job(db: DBSession, *, organization_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    """Expone la vacante propia al router; el repositorio aplica el filtro de tenant."""
    return _require_job(db, organization_id, job_id)


def list_jobs(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    status: JobStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """Devuelve la página de vacantes del tenant y el total sin paginar."""
    jobs = list_job_rows(db, organization_id, status=status, limit=limit, offset=offset)
    total = count_jobs(db, organization_id, status=status)
    return jobs, total


def create_job(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    description: str = "",
    modality: str | None = None,
    location: str | None = None,
    seniority: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Job:
    """Crea una vacante en borrador; el responsable debe ser miembro del tenant."""
    clean_title = title.strip()
    if not clean_title:
        raise JobValidationError("title must not be blank")
    _require_organization_owner(db, organization_id, owner_id)

    job = Job(
        organization_id=organization_id,
        title=clean_title,
        description=description.strip(),
        status=JobStatus.DRAFT,
        modality=modality.strip() if modality is not None else None,
        location=location.strip() if location is not None else None,
        seniority=seniority.strip() if seniority is not None else None,
        owner_id=owner_id,
    )
    db.add(job)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="job.created",
        resource_type="job",
        resource_id=job.id,
    )
    db.commit()
    return job


def update_job(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    title: str | None = None,
    description: str | None = None,
    modality: str | None = None,
    location: str | None = None,
    seniority: str | None = None,
    owner_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> Job:
    """Actualiza campos explícitos; `None` significa «sin cambio»."""
    job = _require_job(db, organization_id, job_id)
    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise JobValidationError("title must not be blank")
        job.title = clean_title
    if description is not None:
        job.description = description.strip()
    if modality is not None:
        job.modality = modality.strip()
    if location is not None:
        job.location = location.strip()
    if seniority is not None:
        job.seniority = seniority.strip()
    if owner_id is not None:
        _require_organization_owner(db, organization_id, owner_id)
        job.owner_id = owner_id

    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="job.updated",
        resource_type="job",
        resource_id=job.id,
    )
    db.commit()
    return job


def add_requirement(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    category: RequirementCategory,
    description: str,
    importance: RequirementImportance,
    expected_level: str | None = None,
    acceptable_evidence: list[str] | None = None,
    weight: float = 0.0,
    weight_justification: str = "",
    actor_id: uuid.UUID | None = None,
) -> JobRequirement:
    """Agrega un requisito con peso justificado cuando es mayor que cero."""
    job = _require_job(db, organization_id, job_id)
    clean_description = description.strip()
    if not clean_description:
        raise JobValidationError("requirement description must not be blank")
    if not math.isfinite(weight) or weight < 0.0 or weight > 1.0:
        raise JobValidationError("weight must be between 0 and 1")
    clean_justification = weight_justification.strip()
    if weight > 0.0 and not clean_justification:
        raise JobValidationError("weight > 0 requires a justification")

    evidence: list[str] = []
    for item in acceptable_evidence or []:
        clean_item = item.strip()
        if not clean_item:
            raise JobValidationError("acceptable evidence must not be blank")
        evidence.append(clean_item)

    requirement = JobRequirement(
        job_id=job.id,
        category=category,
        description=clean_description,
        importance=importance,
        expected_level=expected_level.strip() if expected_level is not None else None,
        acceptable_evidence=evidence,
        weight=weight,
        weight_justification=clean_justification,
    )
    db.add(requirement)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="requirement.added",
        resource_type="requirement",
        resource_id=requirement.id,
    )
    db.commit()
    return requirement


def change_status(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    new_status: JobStatus,
    actor_id: uuid.UUID | None = None,
) -> Job:
    """Aplica solo transiciones permitidas; `archived` es terminal."""
    job = _require_job(db, organization_id, job_id)
    if new_status not in _ALLOWED_TRANSITIONS.get(job.status, frozenset()):
        raise InvalidJobStatusTransitionError
    job.status = new_status
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="job.status_changed",
        resource_type="job",
        resource_id=job.id,
    )
    db.commit()
    return job


def create_version(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> JobVersion:
    """Guarda un snapshot inmutable de la vacante y sus requisitos."""
    job = _require_job(db, organization_id, job_id)
    requirements = list_requirements(db, organization_id, job.id)

    next_version_stmt = (
        select(func.coalesce(func.max(JobVersion.version), 0))
        .join(Job, Job.id == JobVersion.job_id)
        .where(
            Job.organization_id == organization_id,
            JobVersion.job_id == job.id,
        )
    )
    next_version = int(db.scalar(next_version_stmt) or 0) + 1

    snapshot: dict[str, object] = {
        "job": {
            "id": str(job.id),
            "organization_id": str(job.organization_id),
            "title": job.title,
            "description": job.description,
            "status": job.status.value,
            "modality": job.modality,
            "location": job.location,
            "seniority": job.seniority,
            "owner_id": str(job.owner_id),
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        },
        "requirements": [
            {
                "id": str(requirement.id),
                "category": requirement.category.value,
                "description": requirement.description,
                "importance": requirement.importance.value,
                "expected_level": requirement.expected_level,
                "acceptable_evidence": list(requirement.acceptable_evidence),
                "weight": float(requirement.weight),
                "weight_justification": requirement.weight_justification,
                "created_at": requirement.created_at.isoformat(),
                "updated_at": requirement.updated_at.isoformat(),
            }
            for requirement in requirements
        ],
    }

    version = JobVersion(job_id=job.id, version=next_version, snapshot=snapshot)
    db.add(version)
    try:
        db.flush()
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="version.created",
            resource_type="job_version",
            resource_id=version.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise JobVersionConflictError from None
    return version


def update_requirement(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    requirement_id: uuid.UUID,
    category: RequirementCategory | None = None,
    description: str | None = None,
    importance: RequirementImportance | None = None,
    expected_level: str | None = None,
    acceptable_evidence: list[str] | None = None,
    weight: float | None = None,
    weight_justification: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> JobRequirement:
    """Actualiza un requisito propio; `None` significa «sin cambio»."""
    _require_job(db, organization_id, job_id)
    requirement = get_requirement(db, organization_id, requirement_id)
    if requirement is None or requirement.job_id != job_id:
        raise JobNotFoundError

    if description is not None:
        clean_description = description.strip()
        if not clean_description:
            raise JobValidationError("requirement description must not be blank")
        requirement.description = clean_description
    if category is not None:
        requirement.category = category
    if importance is not None:
        requirement.importance = importance
    if expected_level is not None:
        requirement.expected_level = expected_level.strip()

    effective_weight = requirement.weight if weight is None else weight
    if not math.isfinite(effective_weight) or not 0.0 <= effective_weight <= 1.0:
        raise JobValidationError("weight must be between 0 and 1")
    effective_justification = (
        requirement.weight_justification
        if weight_justification is None
        else weight_justification.strip()
    )
    if effective_weight > 0.0 and not effective_justification:
        raise JobValidationError("weight > 0 requires a justification")
    if weight is not None:
        requirement.weight = weight
    if weight_justification is not None:
        requirement.weight_justification = effective_justification

    if acceptable_evidence is not None:
        evidence: list[str] = []
        for item in acceptable_evidence:
            clean_item = item.strip()
            if not clean_item:
                raise JobValidationError("acceptable evidence must not be blank")
            evidence.append(clean_item)
        requirement.acceptable_evidence = evidence

    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="requirement.updated",
        resource_type="requirement",
        resource_id=requirement.id,
    )
    db.commit()
    return requirement


def list_versions(
    db: DBSession, *, organization_id: uuid.UUID, job_id: uuid.UUID
) -> list[JobVersion]:
    """Lista versiones de una vacante verificada en la organización activa."""
    job = _require_job(db, organization_id, job_id)
    return list_job_versions(db, organization_id, job.id)
