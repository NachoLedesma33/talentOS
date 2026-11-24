from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.integrations.models import (
    Integration,
    IntegrationDomainError,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationTenantMismatchError,
)


def get_integration(
    db: DBSession, organization_id: uuid.UUID, integration_id: uuid.UUID
) -> Integration | None:
    """Lee una integración solo si pertenece al tenant autenticado."""
    stmt = select(Integration).where(
        Integration.organization_id == organization_id,
        Integration.id == integration_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_integrations(
    db: DBSession,
    organization_id: uuid.UUID,
    status: IntegrationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Integration]:
    """Lista del tenant con filtro de estado y paginación acotada."""
    stmt = select(Integration).where(Integration.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Integration.status == status)
    stmt = stmt.order_by(Integration.created_at, Integration.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def create_integration(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    provider: IntegrationProvider,
    encrypted_config_ref: str,
    key_id: str,
    config_version: int = 1,
    status: IntegrationStatus = IntegrationStatus.ACTIVE,
) -> Integration:
    """Persiste el token cifrado; la UNIQUE por proveedor evita duplicados."""
    integration = Integration(
        organization_id=organization_id,
        provider=provider,
        encrypted_config_ref=encrypted_config_ref,
        key_id=key_id,
        config_version=config_version,
        status=status,
    )
    db.add(integration)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise IntegrationDomainError("integration_exists") from None
    return integration


def update_integration(
    db: DBSession,
    organization_id: uuid.UUID,
    integration: Integration,
    *,
    expected_version: int,
    encrypted_config_ref: str | None = None,
    key_id: str | None = None,
    status: IntegrationStatus | None = None,
) -> Integration:
    """Aplica un cambio con versión esperada; toda escritura es tenant-scoped."""
    if integration.organization_id != organization_id:
        raise IntegrationTenantMismatchError()
    if integration.config_version != expected_version:
        raise IntegrationDomainError("integration_version_conflict")
    if encrypted_config_ref is not None:
        if key_id is None:
            raise IntegrationDomainError("invalid_integration_config")
        integration.encrypted_config_ref = encrypted_config_ref
        integration.key_id = key_id
        integration.config_version += 1
    if status is not None:
        integration.status = status
    db.flush()
    return integration


__all__ = [
    "create_integration",
    "get_integration",
    "list_integrations",
    "update_integration",
]
