from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.applications import service as applications_service
from app.applications.models import Application, ApplicationStage, StageChange
from app.applications.schemas import (
    ApplicationCreate,
    ApplicationListResponse,
    ApplicationResponse,
    StageChangeRequest,
    StageChangeResponse,
)
from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])

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


def _http_error(exc: applications_service.ApplicationsDomainError) -> HTTPException:
    """Traduce errores del dominio sin filtrar existencia entre organizaciones."""
    if isinstance(
        exc,
        (
            applications_service.ApplicationNotFoundError,
            applications_service.RelatedResourceNotFoundError,
        ),
    ):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado.")
    if isinstance(
        exc,
        (
            applications_service.DuplicateApplicationError,
            applications_service.InvalidStageTransitionError,
        ),
    ):
        return HTTPException(status.HTTP_409_CONFLICT, detail="Conflicto con el estado actual.")
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


@router.get("/", response_model=ApplicationListResponse)
def list_applications(
    active_organization: CurrentOrganization,
    db: DbDependency,
    job_id: Annotated[uuid.UUID | None, Query()] = None,
    candidate_id: Annotated[uuid.UUID | None, Query()] = None,
    stage: Annotated[ApplicationStage | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationListResponse:
    applications, total = applications_service.list_applications(
        db,
        organization_id=active_organization.id,
        job_id=job_id,
        candidate_id=candidate_id,
        stage=stage,
        limit=limit,
        offset=offset,
    )
    return ApplicationListResponse(items=applications, total=total, limit=limit, offset=offset)


@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    _origin: OriginChecked,
    payload: ApplicationCreate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> Application:
    try:
        return applications_service.create_application(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            **payload.model_dump(),
        )
    except applications_service.ApplicationsDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> Application:
    try:
        return applications_service.get_application(
            db, organization_id=active_organization.id, application_id=application_id
        )
    except applications_service.ApplicationsDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{application_id}/history", response_model=list[StageChangeResponse])
def get_history(
    application_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> list[StageChange]:
    try:
        return applications_service.list_stage_changes(
            db, organization_id=active_organization.id, application_id=application_id
        )
    except applications_service.ApplicationsDomainError as exc:
        raise _http_error(exc) from None


@router.post("/{application_id}/stage", response_model=StageChangeResponse)
def change_stage(
    _origin: OriginChecked,
    application_id: uuid.UUID,
    payload: StageChangeRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> StageChange:
    try:
        return applications_service.change_stage(
            db,
            organization_id=active_organization.id,
            application_id=application_id,
            actor_id=actor.id,
            **payload.model_dump(),
        )
    except applications_service.ApplicationsDomainError as exc:
        raise _http_error(exc) from None
