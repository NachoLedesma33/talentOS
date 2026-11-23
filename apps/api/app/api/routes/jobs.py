from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.jobs import service as jobs_service
from app.jobs.models import Job, JobRequirement, JobStatus, JobVersion
from app.jobs.schemas import (
    JobCreate,
    JobListResponse,
    JobResponse,
    JobStatusUpdate,
    JobUpdate,
    JobVersionResponse,
    RequirementCreate,
    RequirementResponse,
    RequirementUpdate,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
WriteMember = Annotated[
    Membership,
    Depends(
        require_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
        )
    ),
]


def _http_error(exc: jobs_service.JobsDomainError) -> HTTPException:
    """Traduce errores del dominio sin filtrar existencia entre organizaciones."""
    if isinstance(exc, jobs_service.JobNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="Vacante no encontrada.")
    if isinstance(exc, jobs_service.InvalidJobStatusTransitionError):
        return HTTPException(status.HTTP_409_CONFLICT, detail="Transición de estado no permitida.")
    if isinstance(exc, jobs_service.JobVersionConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, detail="La versión ya existe.")
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


@router.get("/", response_model=JobListResponse)
def list_jobs(
    active_organization: CurrentOrganization,
    db: DbDependency,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    jobs, total = jobs_service.list_jobs(
        db,
        organization_id=active_organization.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(items=jobs, total=total, limit=limit, offset=offset)


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    _origin: OriginChecked,
    payload: JobCreate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> Job:
    try:
        return jobs_service.create_job(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            **payload.model_dump(),
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> Job:
    try:
        return jobs_service.get_job(db, organization_id=active_organization.id, job_id=job_id)
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    _origin: OriginChecked,
    job_id: uuid.UUID,
    payload: JobUpdate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> Job:
    try:
        return jobs_service.update_job(
            db,
            organization_id=active_organization.id,
            job_id=job_id,
            actor_id=actor.id,
            **payload.model_dump(exclude_unset=True),
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.post(
    "/{job_id}/requirements",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement(
    _origin: OriginChecked,
    job_id: uuid.UUID,
    payload: RequirementCreate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> JobRequirement:
    try:
        return jobs_service.add_requirement(
            db,
            organization_id=active_organization.id,
            job_id=job_id,
            actor_id=actor.id,
            **payload.model_dump(),
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.patch("/{job_id}/requirements/{requirement_id}", response_model=RequirementResponse)
def update_requirement(
    _origin: OriginChecked,
    job_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: RequirementUpdate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> JobRequirement:
    try:
        return jobs_service.update_requirement(
            db,
            organization_id=active_organization.id,
            job_id=job_id,
            requirement_id=requirement_id,
            actor_id=actor.id,
            **payload.model_dump(exclude_unset=True),
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.post("/{job_id}/status", response_model=JobResponse)
def change_status(
    _origin: OriginChecked,
    job_id: uuid.UUID,
    payload: JobStatusUpdate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> Job:
    try:
        return jobs_service.change_status(
            db,
            organization_id=active_organization.id,
            job_id=job_id,
            new_status=payload.status,
            actor_id=actor.id,
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.post(
    "/{job_id}/versions", response_model=JobVersionResponse, status_code=status.HTTP_201_CREATED
)
def create_version(
    _origin: OriginChecked,
    job_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> JobVersion:
    try:
        return jobs_service.create_version(
            db,
            organization_id=active_organization.id,
            job_id=job_id,
            actor_id=actor.id,
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{job_id}/versions", response_model=list[JobVersionResponse])
def list_versions(
    job_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> list[JobVersion]:
    try:
        return jobs_service.list_versions(
            db, organization_id=active_organization.id, job_id=job_id
        )
    except jobs_service.JobsDomainError as exc:
        raise _http_error(exc) from None
