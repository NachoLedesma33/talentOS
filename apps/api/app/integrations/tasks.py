"""Procesamiento diferido de webhooks entrantes.

La tarea abre su propia sesión, rechaza contexto ajeno al tenant, delega en el
servicio y aplica reintentos exponenciales acotados. Solo registra IDs y códigos:
nunca payload, firma, secreto ni traza del proveedor.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.core.logging import log_structured
from app.db.session import SessionLocal
from app.integrations import service as integrations_service
from app.integrations.models import IntegrationDomainError, WebhookEventStatus
from app.integrations.repositories import find_webhook_event
from app.integrations.webhooks import WebhookDomainError, WebhookRetryError
from app.workers.celery_app import celery_app

_MAX_RETRIES = 3
_TRANSIENT_CODE = "transient_processing_failure"
_DEAD_LETTER_CODE = "max_retries_exceeded"


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


__all__ = ["process_webhook_event"]
