from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.integrations.models import (
    Integration,
    IntegrationDomainError,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationTenantMismatchError,
    WebhookEvent,
    WebhookEventStatus,
    WebhookEventType,
)
from app.integrations.webhooks import DuplicateEventError


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


def get_webhook_event(
    db: DBSession,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
) -> WebhookEvent | None:
    """Evento entrante del tenant y la integración; llave de dedupe única."""
    stmt = select(WebhookEvent).where(
        WebhookEvent.organization_id == organization_id,
        WebhookEvent.integration_id == integration_id,
        WebhookEvent.provider == IntegrationProvider.WEBHOOK_INBOUND,
        WebhookEvent.event_id == event_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_webhook_event(
    db: DBSession, integration_id: uuid.UUID, event_id: uuid.UUID
) -> WebhookEvent | None:
    """Localiza por integración y event_id; el tenant se compara después."""
    stmt = select(WebhookEvent).where(
        WebhookEvent.integration_id == integration_id,
        WebhookEvent.provider == IntegrationProvider.WEBHOOK_INBOUND,
        WebhookEvent.event_id == event_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def create_webhook_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
    event_type: WebhookEventType,
    resource_id: uuid.UUID,
    correlation_id: uuid.UUID,
    occurred_at: datetime,
    payload_hash: str,
    status: WebhookEventStatus = WebhookEventStatus.QUEUED,
) -> WebhookEvent:
    """Persiste evidencia saneada; la UNIQUE evita un segundo efecto."""
    event = WebhookEvent(
        organization_id=organization_id,
        integration_id=integration_id,
        provider=IntegrationProvider.WEBHOOK_INBOUND,
        event_id=event_id,
        event_type=event_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        payload_version="1",
        occurred_at=occurred_at,
        status=status,
        attempts=0,
        payload_hash=payload_hash,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicateEventError() from None
    return event


__all__ = [
    "create_integration",
    "create_webhook_event",
    "find_webhook_event",
    "get_integration",
    "get_webhook_event",
    "list_integrations",
    "update_integration",
]
