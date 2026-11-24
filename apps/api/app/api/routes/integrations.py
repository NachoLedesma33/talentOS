"""API REST del núcleo de integraciones.

Router delgado: autenticación, autorización, contratos, servicio y mapeo de
errores. Las respuestas solo contienen metadatos: sin config, token ni secreto.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.logging import log_structured
from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.integrations import service as integrations_service
from app.integrations.models import Integration, IntegrationDomainError, IntegrationStatus
from app.integrations.schemas import (
    IntegrationCreateRequest,
    IntegrationListResponse,
    IntegrationResponse,
    IntegrationUpdateRequest,
)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
ReadMember = Annotated[
    Membership,
    Depends(require_roles(*tuple(MembershipRole))),
]
WriteMember = Annotated[
    Membership,
    Depends(require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)),
]

_NOT_FOUND = "Recurso de integración no encontrado."
_UNAVAILABLE = "Configuración de integración no disponible."
_BAD_REQUEST = "Solicitud inválida."


def _request_id(request: Request) -> str:
    value: object = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


def _correlation_id(request: Request) -> str:
    value: object = getattr(request.state, "correlation_id", None)
    return str(value) if value else "unknown"


def _http_error(exc: IntegrationDomainError) -> HTTPException:
    """Traduce códigos de dominio a HTTP sin exponer mensajes internos."""
    code = exc.code
    if code == "integration_not_found":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if code in {"integration_exists", "integration_version_conflict"}:
        return HTTPException(status.HTTP_409_CONFLICT, detail="Conflicto de integración.")
    if code == "permission_denied":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.")
    if code in {"integration_key_missing", "integration_config_unreadable"}:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_UNAVAILABLE)
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=_BAD_REQUEST)


def _log(
    event: str,
    *,
    request: Request,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID | None,
    result: str,
    error_code: str | None = None,
) -> None:
    """Registra IDs, resultado y código estable; nunca config, token ni secreto."""
    message = f"{event} integration_id={integration_id} result={result}"
    if error_code is not None:
        message += f" error_code={error_code}"
    log_structured(
        logging.INFO if error_code is None else logging.WARNING,
        message,
        request_id=_request_id(request),
        correlation_id=_correlation_id(request),
        organization_id=str(organization_id),
    )


def _summary(integration: Integration) -> IntegrationResponse:
    return IntegrationResponse(
        id=integration.id,
        provider=integration.provider,
        status=integration.status,
        config_version=integration.config_version,
        key_id=integration.key_id,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    request: Request,
    _origin: OriginChecked,
    payload: IntegrationCreateRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> IntegrationResponse:
    """Alta idempotente por proveedor dentro del tenant."""
    try:
        integration = integrations_service.create_integration(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            payload=payload,
        )
    except IntegrationDomainError as exc:
        _log(
            "integration.create",
            request=request,
            organization_id=active_organization.id,
            integration_id=None,
            result="error",
            error_code=exc.code,
        )
        raise _http_error(exc) from None
    _log(
        "integration.create",
        request=request,
        organization_id=active_organization.id,
        integration_id=integration.id,
        result="created",
    )
    return _summary(integration)


@router.get("", response_model=IntegrationListResponse)
def list_integrations(
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
    status_filter: Annotated[IntegrationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IntegrationListResponse:
    """Listado paginado y tenant-scoped; sin configuración sensible."""
    try:
        integrations = integrations_service.list_integrations(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except IntegrationDomainError as exc:
        raise _http_error(exc) from None
    filters = [Integration.organization_id == active_organization.id]
    if status_filter is not None:
        filters.append(Integration.status == status_filter)
    total = db.scalar(select(func.count()).select_from(Integration).where(*filters)) or 0
    return IntegrationListResponse(
        items=[_summary(item) for item in integrations],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{integration_id}", response_model=IntegrationResponse)
def get_integration(
    integration_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
) -> IntegrationResponse:
    """Detalle saneado; cross-tenant y ausente se responden igual."""
    try:
        integration = integrations_service.get_integration(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            integration_id=integration_id,
        )
    except IntegrationDomainError as exc:
        raise _http_error(exc) from None
    return _summary(integration)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
def update_integration(
    request: Request,
    _origin: OriginChecked,
    integration_id: uuid.UUID,
    payload: IntegrationUpdateRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> IntegrationResponse:
    """Recifra config o cambia estado con versión optimista."""
    try:
        integration = integrations_service.update_integration(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            integration_id=integration_id,
            payload=payload,
        )
    except IntegrationDomainError as exc:
        _log(
            "integration.update",
            request=request,
            organization_id=active_organization.id,
            integration_id=integration_id,
            result="error",
            error_code=exc.code,
        )
        raise _http_error(exc) from None
    _log(
        "integration.update",
        request=request,
        organization_id=active_organization.id,
        integration_id=integration.id,
        result="updated",
    )
    return _summary(integration)


__all__ = ["router"]
