"""Procesamiento diferido de webhooks entrantes.

La tarea abre su propia sesión, rechaza contexto ajeno al tenant, delega en el
servicio y aplica reintentos exponenciales acotados. Solo registra IDs y códigos:
nunca payload, firma, secreto ni traza del proveedor.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.core.logging import log_structured
from app.db.session import SessionLocal
from app.integrations import service as integrations_service
from app.integrations.models import (
    IntegrationDomainError,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEventStatus,
)
from app.integrations.repositories import find_webhook_delivery, find_webhook_event
from app.integrations.webhooks import WebhookDomainError, WebhookRetryError
from app.workers.celery_app import celery_app

_MAX_RETRIES = 3
_TRANSIENT_CODE = "transient_processing_failure"
_DEAD_LETTER_CODE = "max_retries_exceeded"


def _delivery_countdown(delivery: WebhookDelivery) -> int:
    """Uses la ventana calculada por el dominio, acotada a 300 s."""
    if delivery.next_attempt_at is None:
        return min(300, int(2 ** max(1, delivery.attempts)))
    remaining = (delivery.next_attempt_at - datetime.now(UTC)).total_seconds()
    return max(1, min(300, round(remaining)))


def _log_event(
    level: int,
    event: str,
    *,
    event_id: uuid.UUID | str,
    organization_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log de una línea: identificadores y código estable, sin payload."""
    message = f"{event} event_id={event_id} result={result}"
    if error_code is not None:
        message += f" error_code={error_code}"
    log_structured(
        level,
        message,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


def _parse_context(
    organization_id: str,
    integration_id: str,
    event_id: str,
    correlation_id: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    try:
        return (
            uuid.UUID(organization_id),
            uuid.UUID(integration_id),
            uuid.UUID(event_id),
            uuid.UUID(correlation_id),
        )
    except (TypeError, ValueError):
        raise WebhookDomainError("invalid_context") from None


def _mark_transient_failure(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    integration_id: uuid.UUID,
    event_id: uuid.UUID,
) -> int:
    """Persiste intento y estado; devuelve el número de intentos acumulado."""
    event = find_webhook_event(db, integration_id, event_id)
    if event is None:
        return 0
    attempts = event.attempts + 1
    exhausted = attempts > _MAX_RETRIES
    event.attempts = attempts
    event.status = (
        WebhookEventStatus.DEAD_LETTER if exhausted else WebhookEventStatus.FAILED
    )
    event.last_error_code = _DEAD_LETTER_CODE if exhausted else _TRANSIENT_CODE
    db.commit()
    return attempts


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="integrations.process_webhook_event",
    max_retries=_MAX_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_webhook_event(
    self: Any,
    organization_id: str,
    integration_id: str,
    event_id: str,
    correlation_id: str,
) -> None:
    """Procesa un evento ya verificado; reintenta solo fallos transitorios."""
    try:
        org_id, integration_uuid, event_uuid, correlation = _parse_context(
            organization_id, integration_id, event_id, correlation_id
        )
    except WebhookDomainError:
        _log_event(
            logging.WARNING,
            "webhook.task_rejected",
            event_id=event_id,
            organization_id=organization_id,
            correlation_id=correlation_id,
            result="aborted",
            error_code="invalid_context",
        )
        return

    db: DBSession = SessionLocal()
    try:
        event = find_webhook_event(db, integration_uuid, event_uuid)
        if event is None:
            _log_event(
                logging.WARNING,
                "webhook.task_rejected",
                event_id=event_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="not_found",
            )
            return
        if event.organization_id != org_id:
            _log_event(
                logging.WARNING,
                "webhook.task_rejected",
                event_id=event_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="organization_mismatch",
            )
            return
        if event.correlation_id != correlation:
            _log_event(
                logging.WARNING,
                "webhook.task_rejected",
                event_id=event_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="correlation_mismatch",
            )
            return

        event.status = WebhookEventStatus.PROCESSING
        db.flush()
        integrations_service.process_webhook_event(
            db,
            organization_id=org_id,
            integration_id=integration_uuid,
            event_id=event_uuid,
            correlation_id=correlation,
        )
        event.status = WebhookEventStatus.PROCESSED
        event.last_error_code = None
        db.commit()
        _log_event(
            logging.INFO,
            "webhook.processed",
            event_id=event_uuid,
            organization_id=org_id,
            correlation_id=correlation,
            result="processed",
        )
    except IntegrationDomainError as exc:
        db.rollback()
        _log_event(
            logging.WARNING,
            "webhook.task_rejected",
            event_id=event_uuid,
            organization_id=org_id,
            correlation_id=correlation,
            result="aborted",
            error_code=exc.code,
        )
    except Exception:
        # Ninguna excepción de librería sube con mensaje del proveedor: solo código.
        db.rollback()
        attempts = _mark_transient_failure(
            db,
            organization_id=org_id,
            integration_id=integration_uuid,
            event_id=event_uuid,
        )
        _log_event(
            logging.ERROR,
            "webhook.task_failed",
            event_id=event_uuid,
            organization_id=org_id,
            correlation_id=correlation,
            result="failed" if attempts <= _MAX_RETRIES else "dead_letter",
            error_code=_TRANSIENT_CODE,
        )
        if attempts <= _MAX_RETRIES:
            # Celery lanza Retry; el exc es un código fijo, nunca datos del evento.
            self.retry(exc=WebhookRetryError(), countdown=2**attempts)
    finally:
        db.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="integrations.deliver_webhook",
    max_retries=_MAX_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def deliver_webhook(
    self: Any,
    delivery_id: str,
    organization_id: str,
    correlation_id: str,
) -> None:
    """Entrega un webhook saliente; reintenta solo si el dominio lo permite."""
    try:
        delivery_uuid = uuid.UUID(delivery_id)
        org_id = uuid.UUID(organization_id)
        correlation = uuid.UUID(correlation_id)
    except (TypeError, ValueError):
        _log_event(
            logging.WARNING,
            "webhook_outbound.task_rejected",
            event_id=delivery_id,
            organization_id=organization_id,
            correlation_id=correlation_id,
            result="aborted",
            error_code="invalid_context",
        )
        return

    db: DBSession = SessionLocal()
    outcome: integrations_service.DeliveryOutcome | None = None
    countdown = 0
    try:
        delivery = find_webhook_delivery(db, delivery_uuid)
        if delivery is None:
            _log_event(
                logging.WARNING,
                "webhook_outbound.task_rejected",
                event_id=delivery_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="webhook_delivery_not_found",
            )
            return
        if delivery.organization_id != org_id:
            _log_event(
                logging.WARNING,
                "webhook_outbound.task_rejected",
                event_id=delivery_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="organization_mismatch",
            )
            return
        if delivery.correlation_id != correlation:
            _log_event(
                logging.WARNING,
                "webhook_outbound.task_rejected",
                event_id=delivery_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="correlation_mismatch",
            )
            return
        if delivery.status is WebhookDeliveryStatus.DEAD_LETTER:
            _log_event(
                logging.INFO,
                "webhook_outbound.task_rejected",
                event_id=delivery_uuid,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="dead_letter",
            )
            return

        outcome = integrations_service.deliver_webhook(
            db,
            delivery_uuid,
            organization_id=org_id,
            correlation_id=correlation,
        )
        countdown = _delivery_countdown(delivery)
        db.commit()
        level = (
            logging.INFO
            if outcome is integrations_service.DeliveryOutcome.DELIVERED
            else logging.WARNING
        )
        _log_event(
            level,
            "webhook_outbound.task_result",
            event_id=delivery_uuid,
            organization_id=org_id,
            correlation_id=correlation,
            result=outcome.value,
        )
    except IntegrationDomainError as exc:
        db.rollback()
        _log_event(
            logging.WARNING,
            "webhook_outbound.task_rejected",
            event_id=delivery_uuid,
            organization_id=org_id,
            correlation_id=correlation,
            result="aborted",
            error_code=exc.code,
        )
    except Exception:
        db.rollback()
        _log_event(
            logging.ERROR,
            "webhook_outbound.task_failed",
            event_id=delivery_uuid,
            organization_id=org_id,
            correlation_id=correlation,
            result="failed",
            error_code="internal_error",
        )
    finally:
        db.close()

    # Fuera del try: la excepción de reintento de Celery no debe ser tragada.
    if outcome is integrations_service.DeliveryOutcome.RETRY_SCHEDULED:
        self.retry(exc=WebhookRetryError(), countdown=countdown)


__all__ = ["deliver_webhook", "process_webhook_event"]
