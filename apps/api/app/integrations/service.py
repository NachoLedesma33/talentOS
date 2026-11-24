"""Servicio de dominio del núcleo de integraciones.

Autoridad: backend. Toda operación verifica membresía activa y usuario activo;
el tenant se toma de la sesión. Sin red, envíos ni webhooks en esta unidad.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy.orm import Session as DBSession

from app.audit.service import record_audit
from app.identity.models import MembershipRole, User, UserStatus
from app.identity.repositories import get_membership
from app.integrations.crypto import current_key_id, encrypt_config
from app.integrations.models import (
    Integration,
    IntegrationDomainError,
    IntegrationStatus,
    IntegrationTenantMismatchError,
)
from app.integrations.repositories import (
    create_integration as persist_integration_row,
)
from app.integrations.repositories import (
    get_integration as get_integration_row,
)
from app.integrations.repositories import (
    list_integrations as list_integration_rows,
)
from app.integrations.repositories import (
    update_integration as persist_integration_update,
)
from app.integrations.schemas import (
    IntegrationCreateRequest,
    IntegrationUpdateRequest,
    config_matches_provider,
    safe_integration_metadata,
)

_WRITE_ROLES = frozenset({MembershipRole.OWNER, MembershipRole.ADMIN})
_MAX_PAGE = 100
_RESOURCE_INTEGRATION = "integration"


class IntegrationServiceError(IntegrationDomainError):
    """Error determinista con código estable; sin datos del tenant ni secretos."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _role(value: MembershipRole | str) -> MembershipRole:
    if isinstance(value, MembershipRole):
        return value
    try:
        return MembershipRole(str(value))
    except ValueError:
        raise IntegrationServiceError("permission_denied") from None


def _require_actor(
    db: DBSession,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    *,
    write: bool,
) -> MembershipRole:
    """Verifica tenant, membresía activa, rol y usuario activo antes de operar."""
    membership = get_membership(db, actor_id, organization_id)
    if membership is None:
        raise IntegrationTenantMismatchError()
    role = _role(actor_role)
    if membership.role is not role:
        raise IntegrationServiceError("permission_denied")
    if write and role not in _WRITE_ROLES:
        raise IntegrationServiceError("permission_denied")
    user = db.get(User, actor_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise IntegrationServiceError("permission_denied")
    return role


def _require_integration(
    db: DBSession, organization_id: uuid.UUID, integration_id: uuid.UUID
) -> Integration:
    integration = get_integration_row(db, organization_id, integration_id)
    if integration is None:
        # Cross-tenant y inexistente se responden igual.
        raise IntegrationTenantMismatchError()
    return integration


def _audit(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    integration: Integration,
) -> None:
    """Audita solo metadatos saneados; jamás config, token ni secreto."""
    safe_integration_metadata(integration)
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=_RESOURCE_INTEGRATION,
        resource_id=integration.id,
    )


def create_integration(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    payload: IntegrationCreateRequest,
) -> Integration:
    """Valida, cifra, persiste y audita una integración del tenant."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    # Clave ausente: fallo determinista antes de escribir cualquier fila.
    current_key_id()
    token, key_id = encrypt_config(
        cast(dict[str, object], payload.config.model_dump(mode="json"))
    )
    integration = persist_integration_row(
        db,
        organization_id=organization_id,
        provider=payload.provider,
        encrypted_config_ref=token,
        key_id=key_id,
    )
    _audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="integration.created",
        integration=integration,
    )
    db.commit()
    return integration


def update_integration(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    payload: IntegrationUpdateRequest,
) -> Integration:
    """Cambia config o estado con versión optimista; recifra si hay config nueva."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    current_key_id()
    integration = _require_integration(db, organization_id, integration_id)
    token: str | None = None
    key_id: str | None = None
    if payload.config is not None:
        if not config_matches_provider(payload.config, integration.provider):
            raise IntegrationServiceError("invalid_integration_config")
        token, key_id = encrypt_config(
            cast(dict[str, object], payload.config.model_dump(mode="json"))
        )
    updated = persist_integration_update(
        db,
        organization_id,
        integration,
        expected_version=payload.expected_version,
        encrypted_config_ref=token,
        key_id=key_id,
        status=payload.status,
    )
    _audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="integration.updated",
        integration=updated,
    )
    db.commit()
    return updated


def get_integration(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
) -> Integration:
    """Detalle de solo lectura para cualquier miembro activo del tenant."""
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    return _require_integration(db, organization_id, integration_id)


def list_integrations(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    status: IntegrationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Integration]:
    """Listado tenant-scoped para cualquier miembro activo."""
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    return list_integration_rows(
        db, organization_id, status=status, limit=min(limit, _MAX_PAGE), offset=offset
    )


__all__ = [
    "IntegrationServiceError",
    "create_integration",
    "get_integration",
    "list_integrations",
    "update_integration",
]
