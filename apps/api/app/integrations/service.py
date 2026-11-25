"""Servicio de dominio del núcleo de integraciones.

Autoridad: backend. Toda operación verifica membresía activa y usuario activo;
el tenant se toma de la sesión. Sin red, envíos ni webhooks en esta unidad.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from sqlalchemy.orm import Session as DBSession

from app.audit.service import record_audit
from app.core.logging import log_structured
from app.identity.models import MembershipRole, User, UserStatus
from app.identity.repositories import get_membership
from app.integrations.crypto import current_key_id, encrypt_config
from app.integrations.models import (
    Integration,
    IntegrationDomainError,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationTenantMismatchError,
    WebhookEvent,
    WebhookEventStatus,
)
from app.integrations.repositories import (
    create_integration as persist_integration_row,
)
from app.integrations.repositories import (
    create_webhook_event as persist_webhook_event_row,
)
from app.integrations.repositories import (
    get_integration as get_integration_row,
)
from app.integrations.repositories import (
    get_webhook_event as get_webhook_event_row,
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
    WebhookAcceptedResponse,
    WebhookEnvelope,
    WebhookEventSummary,
    config_matches_provider,
    safe_integration_metadata,
)
from app.integrations.webhooks import (
    DuplicateEventError,
    WebhookDomainError,
    verify_webhook_request,
)

_WRITE_ROLES = frozenset({MembershipRole.OWNER, MembershipRole.ADMIN})
_MAX_PAGE = 100
_RESOURCE_INTEGRATION = "integration"
_RESOURCE_WEBHOOK_EVENT = "webhook_event"
_BROKER_CODE = "broker_unavailable"
_RETRYABLE_STATUSES = frozenset(
    {WebhookEventStatus.FAILED, WebhookEventStatus.DEAD_LETTER}
)


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


def _require_inbound_integration(
    db: DBSession, integration_id: uuid.UUID
) -> Integration:
    """Resuelve la integración pública por id y proveedor; tenant Sale de la fila."""
    integration = db.get(Integration, integration_id)
    if integration is None or integration.provider is not IntegrationProvider.WEBHOOK_INBOUND:
        # Cross-tenant, proveedor incorrecto y ausente se responden igual.
        raise IntegrationTenantMismatchError()
    return integration


def _require_inbound_for_tenant(
    db: DBSession, organization_id: uuid.UUID, integration_id: uuid.UUID
) -> Integration:
    integration = _require_integration(db, organization_id, integration_id)
    if integration.provider is not IntegrationProvider.WEBHOOK_INBOUND:
        raise IntegrationTenantMismatchError()
    return integration


def _log_webhook(
    event: str,
    *,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
    correlation_id: uuid.UUID,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log de una línea: IDs y códigos estables; nunca payload ni firma."""
    message = (
        f"{event} integration_id={integration_id} event_id={event_id} result={result}"
    )
    if error_code is not None:
        message += f" error_code={error_code}"
    log_structured(
        logging.INFO if error_code is None else logging.WARNING,
        message,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


def _enqueue_webhook_event(event: WebhookEvent) -> None:
    """Encola solo IDs y contexto mínimo; import local evita ciclo con tasks."""
    from app.integrations.tasks import process_webhook_event

    process_webhook_event.delay(
        str(event.organization_id),
        str(event.integration_id),
        str(event.event_id),
        str(event.correlation_id),
    )


def _mark_enqueue_failure(db: DBSession, event: WebhookEvent) -> None:
    event.status = WebhookEventStatus.ENQUEUE_FAILED
    event.last_error_code = _BROKER_CODE
    db.commit()


def _accepted(
    event: WebhookEvent, envelope: WebhookEnvelope, *, duplicate: bool
) -> WebhookAcceptedResponse:
    return WebhookAcceptedResponse(
        event_id=envelope.event_id,
        correlation_id=envelope.correlation_id,
        status=event.status,
        duplicate=duplicate,
    )


def receive_webhook(
    db: DBSession,
    *,
    integration_id: uuid.UUID,
    raw_body: bytes,
    headers: Mapping[str, str],
    now: datetime | None = None,
) -> WebhookAcceptedResponse:
    """Verifica, deduplica, persiste y encola; la firma es la autenticación."""
    integration = _require_inbound_integration(db, integration_id)
    verified = verify_webhook_request(
        integration=integration, raw_body=raw_body, headers=headers, now=now
    )
    envelope = verified.envelope
    organization_id = integration.organization_id

    existing = get_webhook_event_row(
        db, organization_id, integration.id, envelope.event_id
    )
    if existing is not None:
        _log_webhook(
            "webhook.received",
            organization_id=organization_id,
            integration_id=integration.id,
            event_id=envelope.event_id,
            correlation_id=existing.correlation_id,
            result="duplicate",
        )
        return _accepted(existing, envelope, duplicate=True)

    try:
        event = persist_webhook_event_row(
            db,
            organization_id=organization_id,
            integration_id=integration.id,
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            resource_id=envelope.resource_id,
            correlation_id=envelope.correlation_id,
            occurred_at=envelope.occurred_at,
            payload_hash=verified.payload_hash,
        )
    except DuplicateEventError:
        existing = get_webhook_event_row(
            db, organization_id, integration.id, envelope.event_id
        )
        if existing is None:
            raise
        return _accepted(existing, envelope, duplicate=True)

    record_audit(
        db,
        organization_id=organization_id,
        actor_id=None,
        action="webhook.received",
        resource_type=_RESOURCE_WEBHOOK_EVENT,
        resource_id=event.id,
    )
    db.commit()

    try:
        _enqueue_webhook_event(event)
    except Exception:
        # Nunca propagar mensaje ni traza del broker; la evidencia permanece.
        _mark_enqueue_failure(db, event)
        _log_webhook(
            "webhook.enqueue_failed",
            organization_id=organization_id,
            integration_id=integration.id,
            event_id=event.event_id,
            correlation_id=event.correlation_id,
            result="failed",
            error_code=_BROKER_CODE,
        )
        raise WebhookDomainError(_BROKER_CODE) from None

    _log_webhook(
        "webhook.received",
        organization_id=organization_id,
        integration_id=integration.id,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        result="queued",
    )
    return _accepted(event, envelope, duplicate=False)


def process_webhook_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
    correlation_id: uuid.UUID,
) -> WebhookEvent:
    """Handler determinista: valida contexto y audita; no decide negocio."""
    _require_inbound_for_tenant(db, organization_id, integration_id)
    event = get_webhook_event_row(db, organization_id, integration_id, event_id)
    if event is None:
        raise IntegrationTenantMismatchError()
    if event.correlation_id != correlation_id:
        raise WebhookDomainError("correlation_mismatch")
    if event.status is WebhookEventStatus.PROCESSED:
        return event

    # Sin payload, LLM, escritura de dominio ni cambio de etapa: solo evidencia.
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=None,
        action="webhook.processed",
        resource_type=_RESOURCE_WEBHOOK_EVENT,
        resource_id=event.id,
    )
    return event


def retry_webhook_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
) -> WebhookEvent:
    """Reencola un evento fallido o en dead-letter; exige rol de escritura."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    _require_inbound_for_tenant(db, organization_id, integration_id)
    event = get_webhook_event_row(db, organization_id, integration_id, event_id)
    if event is None:
        raise IntegrationTenantMismatchError()
    if event.status not in _RETRYABLE_STATUSES:
        raise WebhookDomainError("webhook_invalid_state")

    event.status = WebhookEventStatus.QUEUED
    event.attempts = 0
    event.last_error_code = None
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="webhook.retry_requested",
        resource_type=_RESOURCE_WEBHOOK_EVENT,
        resource_id=event.id,
    )
    db.commit()
    try:
        _enqueue_webhook_event(event)
    except Exception:
        _mark_enqueue_failure(db, event)
        _log_webhook(
            "webhook.retry_enqueue_failed",
            organization_id=organization_id,
            integration_id=integration_id,
            event_id=event_id,
            correlation_id=event.correlation_id,
            result="failed",
            error_code=_BROKER_CODE,
        )
        raise WebhookDomainError(_BROKER_CODE) from None

    _log_webhook(
        "webhook.retry_requested",
        organization_id=organization_id,
        integration_id=integration_id,
        event_id=event_id,
        correlation_id=event.correlation_id,
        result="queued",
    )
    return event


def webhook_summary(event: WebhookEvent) -> WebhookEventSummary:
    """DTO público del evento: sin payload, firma, secreto ni cabeceras."""
    return WebhookEventSummary(
        id=event.id,
        event_id=event.event_id,
        event_type=event.event_type,
        status=event.status,
        attempts=event.attempts,
        last_error_code=event.last_error_code,
        occurred_at=event.occurred_at,
        received_at=event.received_at,
    )


__all__ = [
    "IntegrationServiceError",
    "create_integration",
    "get_integration",
    "list_integrations",
    "process_webhook_event",
    "receive_webhook",
    "retry_webhook_event",
    "update_integration",
    "webhook_summary",
]
