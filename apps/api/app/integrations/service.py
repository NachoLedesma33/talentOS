"""Servicio de dominio del núcleo de integraciones.

Autoridad: backend. Toda operación verifica membresía activa y usuario activo;
el tenant se toma de la sesión. Sin red, envíos ni webhooks en esta unidad.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import cast
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.audit.service import record_audit
from app.core.logging import log_structured
from app.identity.models import MembershipRole, User, UserStatus
from app.identity.repositories import get_membership
from app.integrations.crypto import current_key_id, decrypt_config, encrypt_config
from app.integrations.email import (
    EmailDeliveryResult,
    EmailMessage,
    EmailSender,
    SandboxEmailSender,
)
from app.integrations.models import (
    EmailApprovalStatus,
    EmailDeliveryStatus,
    EmailDraft,
    EmailDraftExistsError,
    EmailDraftNotFoundError,
    EmailLanguage,
    EmailTemplate,
    Integration,
    IntegrationConfigUnreadableError,
    IntegrationDomainError,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationTenantMismatchError,
    InvalidEmailApprovalTransitionError,
    WebhookDelivery,
    WebhookDeliveryExistsError,
    WebhookDeliveryInvalidStatusError,
    WebhookDeliveryNotFoundError,
    WebhookDeliveryStatus,
    WebhookEvent,
    WebhookEventStatus,
    ensure_email_approval_transition,
)
from app.integrations.outbound import HttpxWebhookSender, WebhookDeliveryResult, WebhookSender
from app.integrations.repositories import (
    count_email_drafts as count_email_rows,
)
from app.integrations.repositories import (
    count_webhook_deliveries as count_delivery_rows,
)
from app.integrations.repositories import (
    create_email_draft as persist_email_draft_row,
)
from app.integrations.repositories import (
    create_integration as persist_integration_row,
)
from app.integrations.repositories import (
    create_webhook_delivery as persist_webhook_delivery_row,
)
from app.integrations.repositories import (
    create_webhook_event as persist_webhook_event_row,
)
from app.integrations.repositories import (
    find_email_draft as find_email_row,
)
from app.integrations.repositories import (
    find_webhook_delivery as find_delivery_row,
)
from app.integrations.repositories import (
    get_email_draft as get_email_row,
)
from app.integrations.repositories import (
    get_integration as get_integration_row,
)
from app.integrations.repositories import (
    get_webhook_delivery as get_delivery_row,
)
from app.integrations.repositories import (
    get_webhook_delivery_by_event as get_delivery_by_event_row,
)
from app.integrations.repositories import (
    get_webhook_event as get_webhook_event_row,
)
from app.integrations.repositories import (
    list_email_drafts as list_email_rows,
)
from app.integrations.repositories import (
    list_integrations as list_integration_rows,
)
from app.integrations.repositories import (
    list_webhook_deliveries as list_delivery_rows,
)
from app.integrations.repositories import (
    update_integration as persist_integration_update,
)
from app.integrations.schemas import (
    EmailDraftCreateRequest,
    EmailDraftDetail,
    EmailDraftListResponse,
    EmailDraftSummary,
    EmailSandboxConfig,
    IntegrationCreateRequest,
    IntegrationUpdateRequest,
    OutboundEventRequest,
    WebhookAcceptedResponse,
    WebhookDeliveryListResponse,
    WebhookDeliverySummary,
    WebhookEnvelope,
    WebhookEventSummary,
    WebhookOutboundConfig,
    config_matches_provider,
    safe_integration_metadata,
)
from app.integrations.webhooks import (
    DuplicateEventError,
    WebhookDomainError,
    canonical_payload_hash,
    verify_webhook_request,
)

_WRITE_ROLES = frozenset({MembershipRole.OWNER, MembershipRole.ADMIN})
_MAX_PAGE = 100
_RESOURCE_INTEGRATION = "integration"
_RESOURCE_EMAIL_DRAFT = "email_draft"
_RESOURCE_WEBHOOK_EVENT = "webhook_event"
_RESOURCE_WEBHOOK_DELIVERY = "webhook_delivery"
_BROKER_CODE = "broker_unavailable"
_RETRYABLE_STATUSES = frozenset(
    {WebhookEventStatus.FAILED, WebhookEventStatus.DEAD_LETTER}
)
_DELIVERY_RETRYABLE_STATUSES = frozenset(
    {WebhookDeliveryStatus.FAILED, WebhookDeliveryStatus.DEAD_LETTER}
)
_DELIVERY_SENDABLE_STATUSES = frozenset(
    {
        WebhookDeliveryStatus.PENDING,
        WebhookDeliveryStatus.SENDING,
        WebhookDeliveryStatus.FAILED,
        WebhookDeliveryStatus.DEAD_LETTER,
    }
)
_TRANSIENT_STATUS_CODES = frozenset({408, 429})
_TRANSIENT_ERROR_CODES = frozenset({"provider_timeout", "provider_unavailable"})
_MAX_DELIVERY_ATTEMPTS = 3
_MAX_BACKOFF_SECONDS = 300
_PAYLOAD_VERSION = "1"


class DeliveryOutcome(StrEnum):
    """Resultado observable de un intento de entrega saliente."""

    DELIVERED = "delivered"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTER = "dead_letter"


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


def _require_outbound_for_tenant(
    db: DBSession, organization_id: uuid.UUID, integration_id: uuid.UUID
) -> Integration:
    """Solo integraciones salientes activas y del tenant autenticado."""
    integration = _require_integration(db, organization_id, integration_id)
    if integration.provider is not IntegrationProvider.WEBHOOK_OUTBOUND:
        raise IntegrationTenantMismatchError()
    if integration.status is not IntegrationStatus.ACTIVE:
        raise IntegrationServiceError("integration_inactive")
    return integration


def read_outbound_config(integration: Integration) -> WebhookOutboundConfig:
    """Descifra y valida el config saliente; secretos nunca salen de esta función."""
    if integration.provider is not IntegrationProvider.WEBHOOK_OUTBOUND:
        raise IntegrationTenantMismatchError()
    raw = decrypt_config(integration.encrypted_config_ref)
    try:
        return WebhookOutboundConfig.model_validate(raw)
    except ValidationError:
        raise IntegrationConfigUnreadableError() from None


def _endpoint_snapshot(endpoint: object) -> str:
    """URL audible sin userinfo, query ni fragmento: sin secretos en la BD."""
    try:
        parts = urlsplit(str(endpoint))
        port = parts.port
    except ValueError:
        raise IntegrationServiceError("invalid_integration_config") from None
    host = parts.hostname
    if parts.scheme not in {"http", "https"} or not host:
        raise IntegrationServiceError("invalid_integration_config")
    host_part = f"[{host}]" if ":" in host else host
    port_part = f":{port}" if port is not None else ""
    path = parts.path or "/"
    return f"{parts.scheme}://{host_part}{port_part}{path}"


def _outbound_request(
    *,
    event_id: uuid.UUID,
    event_type: object,
    resource_id: uuid.UUID,
    correlation_id: uuid.UUID,
    payload: Mapping[str, object],
) -> OutboundEventRequest:
    """Valida el contrato estricto; errores de forma nunca exponen payload."""
    try:
        return OutboundEventRequest.model_validate(
            {
                "event_id": event_id,
                "event_type": event_type,
                "resource_id": resource_id,
                "correlation_id": correlation_id,
                "payload": dict(payload),
            }
        )
    except (ValidationError, TypeError, ValueError):
        raise IntegrationServiceError("invalid_outbound_payload") from None


def _outbound_body(delivery: WebhookDelivery) -> bytes:
    """Envelope SDD 11.1 + payload mínimo de metadatos; sin texto libre."""
    created_at = delivery.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    occurred_at = created_at.astimezone(UTC)
    safe_payload = validate_safe_payload(
        {
            "event_type": delivery.event_type.value,
            "resource_id": str(delivery.resource_id),
            "payload_hash": delivery.payload_hash,
        }
    )
    envelope = {
        "event_id": str(delivery.event_id),
        "event_type": delivery.event_type.value,
        "organization_id": str(delivery.organization_id),
        "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
        "resource_id": str(delivery.resource_id),
        "correlation_id": str(delivery.correlation_id),
        "payload_version": _PAYLOAD_VERSION,
        "payload": safe_payload,
    }
    return json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _outbound_headers(
    delivery: WebhookDelivery,
    config: WebhookOutboundConfig,
    body: bytes,
    key_id: str,
) -> dict[str, str]:
    """Firma el cuerpo exacto enviado; la firma viaja como prefijo sha256=."""
    signature = hmac.new(config.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-TalentOS-Key-ID": key_id,
        "X-TalentOS-Event-ID": str(delivery.event_id),
        "X-TalentOS-Timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "X-TalentOS-Correlation-ID": str(delivery.correlation_id),
        "X-TalentOS-Signature": f"sha256={signature}",
    }


def _log_delivery(
    event: str,
    *,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    delivery_id: uuid.UUID,
    correlation_id: uuid.UUID,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log de una línea: IDs y códigos estables; nunca cuerpo ni secreto."""
    message = (
        f"{event} delivery_id={delivery_id} integration_id={integration_id} result={result}"
    )
    if error_code is not None:
        message += f" error_code={error_code}"
    log_structured(
        logging.INFO if error_code is None else logging.WARNING,
        message,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


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


def create_outbound_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
    event_type: object,
    resource_id: uuid.UUID,
    correlation_id: uuid.UUID,
    payload: Mapping[str, object],
) -> WebhookDelivery:
    """Escribe el outbox en la transacción del llamador; el llamador hace commit."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    integration = _require_outbound_for_tenant(db, organization_id, integration_id)
    request = _outbound_request(
        event_id=event_id,
        event_type=event_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    config = read_outbound_config(integration)
    snapshot = _endpoint_snapshot(config.endpoint)

    existing = get_delivery_by_event_row(
        db, organization_id, integration_id, request.event_id
    )
    if existing is not None:
        return existing

    payload_hash = canonical_payload_hash(request.payload)
    try:
        delivery = persist_webhook_delivery_row(
            db,
            organization_id=organization_id,
            integration_id=integration_id,
            event_id=request.event_id,
            event_type=request.event_type,
            resource_id=request.resource_id,
            correlation_id=request.correlation_id,
            endpoint_snapshot=snapshot,
            payload_hash=payload_hash,
        )
    except WebhookDeliveryExistsError:
        # Carrera de dos productores con el mismo event_id: un solo efecto.
        existing = get_delivery_by_event_row(
            db, organization_id, integration_id, request.event_id
        )
        if existing is None:
            raise
        return existing

    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="webhook_outbound.queued",
        resource_type=_RESOURCE_WEBHOOK_DELIVERY,
        resource_id=delivery.id,
    )
    _log_delivery(
        "webhook_outbound.queued",
        organization_id=organization_id,
        integration_id=integration_id,
        delivery_id=delivery.id,
        correlation_id=request.correlation_id,
        result="queued",
    )
    return delivery


def deliver_webhook(
    db: DBSession,
    delivery_id: uuid.UUID,
    *,
    organization_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    sender: WebhookSender | None = None,
) -> DeliveryOutcome:
    """Firma, envía y registra el intento; el llamador es dueño del commit."""
    delivery = find_delivery_row(db, delivery_id)
    if delivery is None:
        raise WebhookDeliveryNotFoundError()
    if organization_id is not None and delivery.organization_id != organization_id:
        raise WebhookDeliveryNotFoundError()
    if correlation_id is not None and delivery.correlation_id != correlation_id:
        raise IntegrationServiceError("correlation_mismatch")
    if delivery.status is WebhookDeliveryStatus.DELIVERED:
        raise WebhookDeliveryInvalidStatusError()
    if delivery.status not in _DELIVERY_SENDABLE_STATUSES:
        raise WebhookDeliveryInvalidStatusError()

    integration = _require_outbound_for_tenant(
        db, delivery.organization_id, delivery.integration_id
    )
    config = read_outbound_config(integration)
    body = _outbound_body(delivery)
    headers = _outbound_headers(delivery, config, body, integration.key_id)

    delivery.status = WebhookDeliveryStatus.SENDING
    db.flush()
    used_sender = sender if sender is not None else HttpxWebhookSender()
    try:
        result = used_sender.send(str(config.endpoint), headers, body)
    except Exception:
        # Ninguna excepción del adaptador sube con mensaje del proveedor.
        result = WebhookDeliveryResult(None, "provider_timeout")

    delivery.last_status_code = result.status_code
    now = datetime.now(UTC)
    if result.succeeded:
        delivery.status = WebhookDeliveryStatus.DELIVERED
        delivery.delivered_at = now
        delivery.last_error_code = None
        delivery.next_attempt_at = None
        record_audit(
            db,
            organization_id=delivery.organization_id,
            actor_id=None,
            action="webhook_outbound.delivered",
            resource_type=_RESOURCE_WEBHOOK_DELIVERY,
            resource_id=delivery.id,
        )
        _log_delivery(
            "webhook_outbound.delivered",
            organization_id=delivery.organization_id,
            integration_id=delivery.integration_id,
            delivery_id=delivery.id,
            correlation_id=delivery.correlation_id,
            result=DeliveryOutcome.DELIVERED.value,
        )
        return DeliveryOutcome.DELIVERED

    code = result.status_code
    transient = (
        result.error_code in _TRANSIENT_ERROR_CODES
        or (code is not None and code in _TRANSIENT_STATUS_CODES)
        or (code is not None and code >= 500)
    )
    attempts = delivery.attempts + 1
    delivery.attempts = attempts
    delivery.last_error_code = result.error_code or "provider_rejected"
    if transient and attempts < _MAX_DELIVERY_ATTEMPTS:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.next_attempt_at = now + timedelta(
            seconds=min(_MAX_BACKOFF_SECONDS, 2**attempts)
        )
        outcome = DeliveryOutcome.RETRY_SCHEDULED
    else:
        delivery.status = WebhookDeliveryStatus.DEAD_LETTER
        delivery.next_attempt_at = None
        outcome = DeliveryOutcome.DEAD_LETTER

    _log_delivery(
        "webhook_outbound.failed",
        organization_id=delivery.organization_id,
        integration_id=delivery.integration_id,
        delivery_id=delivery.id,
        correlation_id=delivery.correlation_id,
        result=outcome.value,
        error_code=delivery.last_error_code,
    )
    return outcome


def list_outbound_deliveries(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    status: WebhookDeliveryStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> WebhookDeliveryListResponse:
    """Listado tenant-scoped sin payload; estado visible para diagnóstico."""
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    _require_outbound_for_tenant(db, organization_id, integration_id)
    items = list_delivery_rows(
        db,
        organization_id,
        integration_id,
        status=status,
        limit=min(limit, _MAX_PAGE),
        offset=offset,
    )
    total = count_delivery_rows(db, organization_id, integration_id, status=status)
    return WebhookDeliveryListResponse(
        items=[outbound_summary(item) for item in items],
        total=total,
        limit=min(limit, _MAX_PAGE),
        offset=offset,
    )


def _enqueue_webhook_delivery(delivery: WebhookDelivery) -> None:
    """Encola solo IDs y contexto mínimo; import local evita ciclo con tasks."""
    from app.integrations.tasks import deliver_webhook

    deliver_webhook.delay(
        str(delivery.id),
        str(delivery.organization_id),
        str(delivery.correlation_id),
    )


def retry_outbound_delivery(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    delivery_id: uuid.UUID,
) -> WebhookDelivery:
    """Reintento manual: vuelve a pending, conserva intentos y evidencia."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    integration = _require_outbound_for_tenant(db, organization_id, integration_id)
    delivery = get_delivery_row(db, organization_id, integration.id, delivery_id)
    if delivery is None:
        raise WebhookDeliveryNotFoundError()
    if delivery.status not in _DELIVERY_RETRYABLE_STATUSES:
        raise WebhookDeliveryInvalidStatusError()

    delivery.status = WebhookDeliveryStatus.PENDING
    delivery.next_attempt_at = None
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="webhook_outbound.retry_requested",
        resource_type=_RESOURCE_WEBHOOK_DELIVERY,
        resource_id=delivery.id,
    )
    db.commit()
    try:
        _enqueue_webhook_delivery(delivery)
    except Exception:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.last_error_code = _BROKER_CODE
        db.commit()
        _log_delivery(
            "webhook_outbound.retry_enqueue_failed",
            organization_id=organization_id,
            integration_id=integration.id,
            delivery_id=delivery.id,
            correlation_id=delivery.correlation_id,
            result="failed",
            error_code=_BROKER_CODE,
        )
        raise WebhookDomainError(_BROKER_CODE) from None

    _log_delivery(
        "webhook_outbound.retry_requested",
        organization_id=organization_id,
        integration_id=integration.id,
        delivery_id=delivery.id,
        correlation_id=delivery.correlation_id,
        result="queued",
    )
    return delivery


def outbound_summary(delivery: WebhookDelivery) -> WebhookDeliverySummary:
    """DTO público de la entrega; sin endpoint, config, payload ni respuesta."""
    return WebhookDeliverySummary(
        id=delivery.id,
        event_id=delivery.event_id,
        event_type=delivery.event_type,
        status=delivery.status,
        attempts=delivery.attempts,
        last_error_code=delivery.last_error_code,
        last_status_code=delivery.last_status_code,
        created_at=delivery.created_at,
        delivered_at=delivery.delivered_at,
    )


_EMAIL_LABELS: dict[EmailLanguage, dict[EmailTemplate, str]] = {
    EmailLanguage.ES: {
        EmailTemplate.INITIAL_CONTACT: "Contacto inicial",
        EmailTemplate.INTERVIEW_INVITE: "Invitación a entrevista",
        EmailTemplate.FOLLOW_UP: "Seguimiento",
    },
    EmailLanguage.EN: {
        EmailTemplate.INITIAL_CONTACT: "Initial contact",
        EmailTemplate.INTERVIEW_INVITE: "Interview invitation",
        EmailTemplate.FOLLOW_UP: "Follow-up",
    },
}
_EMAIL_TOPIC_LABEL = {
    EmailLanguage.ES: "Tema",
    EmailLanguage.EN: "Topic",
}
_EMAIL_CTA_LABEL = {
    EmailLanguage.ES: "Acción",
    EmailLanguage.EN: "Next step",
}
_EMAIL_FOOTER = {
    EmailLanguage.ES: "Mensaje generado en el entorno sandbox de TalentOS.",
    EmailLanguage.EN: "Message generated in the TalentOS sandbox environment.",
}


@dataclass(frozen=True)
class EmailDraftCreation:
    """Resultado de crear un borrador: `created=False` significa idempotente."""

    draft: EmailDraft
    created: bool


def _render_email_text(
    *,
    template: EmailTemplate,
    topic: str,
    language: EmailLanguage,
    call_to_action: str,
) -> str:
    """Texto determinista: solo plantilla, tema, idioma y CTA saneados."""
    return "\n".join(
        (
            _EMAIL_LABELS[language][template],
            f"{_EMAIL_TOPIC_LABEL[language]}: {topic}",
            f"{_EMAIL_CTA_LABEL[language]}: {call_to_action}",
            _EMAIL_FOOTER[language],
        )
    )


def _render_email_subject(
    *, template: EmailTemplate, topic: str, language: EmailLanguage
) -> str:
    label = _EMAIL_LABELS[language][template]
    return f"[TalentOS][{language.value}] {label}: {topic}"[:200]


def _email_body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_email_for_tenant(
    db: DBSession, organization_id: uuid.UUID, integration_id: uuid.UUID
) -> Integration:
    """Solo integraciones `email_sandbox` activas y del tenant autenticado."""
    integration = _require_integration(db, organization_id, integration_id)
    if integration.provider is not IntegrationProvider.EMAIL_SANDBOX:
        # Proveedor incorrecto, ausente y cross-tenant se responden igual.
        raise IntegrationTenantMismatchError()
    if integration.status is not IntegrationStatus.ACTIVE:
        raise IntegrationServiceError("integration_inactive")
    try:
        config = EmailSandboxConfig.model_validate(
            decrypt_config(integration.encrypted_config_ref)
        )
    except (ValidationError, IntegrationConfigUnreadableError):
        raise IntegrationServiceError("invalid_integration_config") from None
    if config.sink != "local_log":
        raise IntegrationServiceError("invalid_integration_config")
    return integration


def _require_email_draft(
    db: DBSession,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> EmailDraft:
    draft = get_email_row(db, organization_id, integration_id, draft_id)
    if draft is None:
        raise EmailDraftNotFoundError()
    return draft


def _log_email(
    event: str,
    *,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    draft_id: uuid.UUID,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log de una línea: IDs y códigos estables; nunca asunto, texto ni correo."""
    message = f"{event} integration_id={integration_id} draft_id={draft_id} result={result}"
    if error_code is not None:
        message += f" error_code={error_code}"
    log_structured(
        logging.INFO if error_code is None else logging.WARNING,
        message,
        correlation_id=str(draft_id),
        organization_id=str(organization_id),
    )


def create_email_draft(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    payload: EmailDraftCreateRequest,
) -> EmailDraftCreation:
    """Crea un borrador pendiente; duplicados devuelven la fila existente."""
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    _require_email_for_tenant(db, organization_id, integration_id)
    text = _render_email_text(
        template=payload.template,
        topic=payload.topic,
        language=payload.language,
        call_to_action=payload.call_to_action,
    )
    body_hash = _email_body_hash(text)
    subject = _render_email_subject(
        template=payload.template, topic=payload.topic, language=payload.language
    )
    existing = find_email_row(
        db,
        organization_id=organization_id,
        integration_id=integration_id,
        candidate_id=payload.candidate_id,
        template=payload.template,
        topic=payload.topic,
        language=payload.language,
        call_to_action=payload.call_to_action,
    )
    if existing is not None:
        return EmailDraftCreation(existing, False)

    try:
        draft = persist_email_draft_row(
            db,
            organization_id=organization_id,
            integration_id=integration_id,
            candidate_id=payload.candidate_id,
            template=payload.template,
            topic=payload.topic,
            language=payload.language,
            call_to_action=payload.call_to_action,
            subject=subject,
            body_hash=body_hash,
            requested_by=actor_id,
        )
    except EmailDraftExistsError:
        existing = find_email_row(
            db,
            organization_id=organization_id,
            integration_id=integration_id,
            candidate_id=payload.candidate_id,
            template=payload.template,
            topic=payload.topic,
            language=payload.language,
            call_to_action=payload.call_to_action,
        )
        if existing is None:
            raise
        return EmailDraftCreation(existing, False)

    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="email.draft_created",
        resource_type=_RESOURCE_EMAIL_DRAFT,
        resource_id=draft.id,
    )
    _log_email(
        "email.draft_created",
        organization_id=organization_id,
        integration_id=integration_id,
        draft_id=draft.id,
        result="created",
    )
    db.commit()
    return EmailDraftCreation(draft, True)


def decide_email_draft(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    draft_id: uuid.UUID,
    decision: EmailApprovalStatus | str,
) -> EmailDraft:
    """Aprueba o rechaza; nunca envía y nunca permite autoaprobación."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    _require_email_for_tenant(db, organization_id, integration_id)
    draft = _require_email_draft(db, organization_id, integration_id, draft_id)
    try:
        target = EmailApprovalStatus(decision)
    except ValueError:
        raise IntegrationServiceError("email_invalid_state") from None
    if draft.requested_by is not None and draft.requested_by == actor_id:
        raise IntegrationServiceError("email_self_approval")
    try:
        ensure_email_approval_transition(draft.approval_status, target)
        draft.decide(target, actor_id, datetime.now(UTC))
    except InvalidEmailApprovalTransitionError as exc:
        raise IntegrationServiceError(exc.code) from None

    action = "email.approved" if target is EmailApprovalStatus.APPROVED else "email.rejected"
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=_RESOURCE_EMAIL_DRAFT,
        resource_id=draft.id,
    )
    _log_email(
        action,
        organization_id=organization_id,
        integration_id=integration_id,
        draft_id=draft.id,
        result=target.value,
    )
    db.commit()
    return draft


def send_email_draft(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    draft_id: uuid.UUID,
    sender: EmailSender | None = None,
) -> EmailDraft:
    """Envía solo tras aprobación humana; fallos quedan registrados y auditados."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    _require_email_for_tenant(db, organization_id, integration_id)
    draft = _require_email_draft(db, organization_id, integration_id, draft_id)
    if draft.approval_status is not EmailApprovalStatus.APPROVED:
        raise IntegrationServiceError("email_not_approved")
    if draft.delivery_status is EmailDeliveryStatus.SENT:
        raise IntegrationServiceError("email_already_sent")

    text = _render_email_text(
        template=draft.template,
        topic=draft.topic,
        language=draft.language,
        call_to_action=draft.call_to_action,
    )
    if _email_body_hash(text) != draft.body_hash:
        raise IntegrationServiceError("email_body_mismatch")
    message = EmailMessage(
        candidate_id=draft.candidate_id, subject=draft.subject, text=text
    )

    used_sender = sender if sender is not None else SandboxEmailSender()
    try:
        result = used_sender.send(message)
    except Exception:
        # Ningún mensaje del adaptador sube con texto, correo ni secreto.
        result = EmailDeliveryResult(None, "provider_failed")

    draft.attempts += 1
    if result.succeeded:
        draft.delivery_status = EmailDeliveryStatus.SENT
        draft.sent_at = datetime.now(UTC)
        draft.last_error_code = None
        action = "email.sent"
    else:
        draft.delivery_status = EmailDeliveryStatus.FAILED
        draft.last_error_code = result.error_code or "provider_rejected"
        action = "email.send_failed"

    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=_RESOURCE_EMAIL_DRAFT,
        resource_id=draft.id,
    )
    _log_email(
        action,
        organization_id=organization_id,
        integration_id=integration_id,
        draft_id=draft.id,
        result=draft.delivery_status.value,
        error_code=draft.last_error_code,
    )
    db.commit()
    return draft


def email_summary(draft: EmailDraft) -> EmailDraftSummary:
    """DTO de listado: sin asunto, cuerpo, hash ni actores."""
    return EmailDraftSummary(
        id=draft.id,
        candidate_id=draft.candidate_id,
        template=draft.template,
        approval_status=draft.approval_status,
        delivery_status=draft.delivery_status,
        attempts=draft.attempts,
        created_at=draft.created_at,
    )


def email_detail(draft: EmailDraft) -> EmailDraftDetail:
    """DTO de detalle saneado; el texto completo nunca se persiste ni se devuelve."""
    return EmailDraftDetail(
        id=draft.id,
        candidate_id=draft.candidate_id,
        template=draft.template,
        approval_status=draft.approval_status,
        delivery_status=draft.delivery_status,
        attempts=draft.attempts,
        created_at=draft.created_at,
        integration_id=draft.integration_id,
        topic=draft.topic,
        language=draft.language,
        call_to_action=draft.call_to_action,
        subject=draft.subject,
        body_hash=draft.body_hash,
        requested_by=draft.requested_by,
        decided_by=draft.decided_by,
        decided_at=draft.decided_at,
        last_error_code=draft.last_error_code,
        sent_at=draft.sent_at,
        updated_at=draft.updated_at,
    )


def get_email_draft(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> EmailDraft:
    """Detalle de solo lectura para cualquier miembro activo del tenant."""
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    _require_email_for_tenant(db, organization_id, integration_id)
    return _require_email_draft(db, organization_id, integration_id, draft_id)


def list_email_drafts(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    integration_id: uuid.UUID,
    approval_status: EmailApprovalStatus | None = None,
    delivery_status: EmailDeliveryStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> EmailDraftListResponse:
    """Listado paginado y tenant-scoped; sin cuerpo ni destinatario."""
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    _require_email_for_tenant(db, organization_id, integration_id)
    page_size = min(limit, _MAX_PAGE)
    items = list_email_rows(
        db,
        organization_id,
        integration_id,
        approval_status=approval_status,
        delivery_status=delivery_status,
        limit=page_size,
        offset=offset,
    )
    total = count_email_rows(
        db,
        organization_id,
        integration_id,
        approval_status=approval_status,
        delivery_status=delivery_status,
    )
    return EmailDraftListResponse(
        items=[email_summary(item) for item in items],
        total=total,
        limit=page_size,
        offset=offset,
    )


__all__ = [
    "DeliveryOutcome",
    "EmailDraftCreation",
    "IntegrationServiceError",
    "create_email_draft",
    "create_integration",
    "create_outbound_event",
    "decide_email_draft",
    "deliver_webhook",
    "email_detail",
    "email_summary",
    "get_email_draft",
    "get_integration",
    "list_email_drafts",
    "list_integrations",
    "list_outbound_deliveries",
    "outbound_summary",
    "process_webhook_event",
    "read_outbound_config",
    "receive_webhook",
    "send_email_draft",
    "retry_outbound_delivery",
    "retry_webhook_event",
    "update_integration",
    "webhook_summary",
]
