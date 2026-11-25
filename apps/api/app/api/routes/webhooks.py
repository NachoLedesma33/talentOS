"""Endpoint público de webhooks entrantes.

Sin sesión ni CSRF: la autenticación es la firma HMAC. El router solo lee el
cuerpo crudo, delega en el servicio y traduce códigos a HTTP sin exponer
mensajes internos, payload, secreto ni firma.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.core.logging import log_structured
from app.db.session import get_db
from app.integrations import service as integrations_service
from app.integrations.models import IntegrationDomainError
from app.integrations.schemas import WebhookAcceptedResponse

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

DbDependency = Annotated[DBSession, Depends(get_db)]

_MESSAGES = {
    400: "Solicitud de webhook inválida.",
    401: "Firma de webhook no válida.",
    403: "Rol insuficiente.",
    404: "Integración no encontrada.",
    409: "Conflicto de webhook.",
    503: "Servicio de webhook no disponible.",
}
_STATUS_BY_CODE = {
    "invalid_signature": 401,
    "unknown_key_id": 401,
    "integration_not_found": 404,
    "invalid_envelope": 400,
    "stale_event": 400,
    "duplicate_event": 409,
    "permission_denied": 403,
    "webhook_invalid_state": 409,
    "integration_config_unreadable": 503,
    "integration_key_missing": 503,
    "broker_unavailable": 503,
}


def _request_id(request: Request) -> str:
    value: object = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


def _http_error(exc: IntegrationDomainError) -> HTTPException:
    code = exc.code
    status_code = _STATUS_BY_CODE.get(code, 400)
    return HTTPException(
        status_code=status_code,
        detail=_MESSAGES.get(status_code, _MESSAGES[400]),
    )


def _log_rejection(request: Request, integration_id: uuid.UUID, code: str) -> None:
    """Registra IDs y código estable; nunca cabeceras de firma ni cuerpo."""
    log_structured(
        logging.WARNING,
        f"webhook.rejected integration_id={integration_id} result=rejected error_code={code}",
        request_id=_request_id(request),
    )


@router.post(
    "/inbound/{integration_id}",
    response_model=WebhookAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def inbound_webhook(
    integration_id: uuid.UUID,
    request: Request,
    db: DbDependency,
) -> WebhookAcceptedResponse:
    """Verifica firma/tiempo/envelope, deduplica y encola; sin efectos en la request."""
    raw_body = await request.body()
    try:
        return integrations_service.receive_webhook(
            db,
            integration_id=integration_id,
            raw_body=raw_body,
            headers=request.headers,
        )
    except IntegrationDomainError as exc:
        _log_rejection(request, integration_id, exc.code)
        raise _http_error(exc) from None


__all__ = ["router"]
