"""Verificación criptográfica y anti-replay de webhooks entrantes.

Autoridad: la fila de `Integration`. El cuerpo crudo solo se usa para HMAC y
parseo; nunca se registra ni se guarda. La firma, el secreto y el payload no
aparecen en logs, errores ni respuestas.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from app.integrations.crypto import decrypt_config
from app.integrations.models import (
    Integration,
    IntegrationConfigUnreadableError,
    IntegrationDomainError,
    IntegrationProvider,
    IntegrationTenantMismatchError,
)
from app.integrations.schemas import WebhookEnvelope, WebhookInboundConfig

_SIGNATURE_PREFIX = "sha256="


class WebhookDomainError(IntegrationDomainError):
    """Error tipado de recepción; `code` estable y sin datos del proveedor."""

    code = "invalid_envelope"

    def __init__(self, code: str | None = None) -> None:
        self.code = code if code is not None else type(self).code
        super().__init__(self.code)


class InvalidSignatureError(WebhookDomainError):
    code = "invalid_signature"


class StaleEventError(WebhookDomainError):
    code = "stale_event"


class DuplicateEventError(WebhookDomainError):
    code = "duplicate_event"


class UnknownKeyIdError(WebhookDomainError):
    code = "unknown_key_id"


class InvalidEnvelopeError(WebhookDomainError):
    code = "invalid_envelope"


class WebhookRetryError(WebhookDomainError):
    code = "webhook_retry"


@dataclass(frozen=True)
class WebhookHeaders:
    """Cabeceras obligatorias; `organization_id` nunca se lee de aquí."""

    key_id: str
    event_id: uuid.UUID
    timestamp: str
    signature: str


@dataclass(frozen=True)
class VerifiedWebhook:
    """Resultado de verificación: envelope saneado y hash canónico."""

    envelope: WebhookEnvelope
    payload_hash: str


def parse_headers(headers: Mapping[str, str]) -> WebhookHeaders:
    """Extrae cabeceras obligatorias; sin valores en mensajes de error."""
    key_id = headers.get("X-TalentOS-Key-ID", "").strip()
    raw_event_id = headers.get("X-TalentOS-Event-ID", "").strip()
    timestamp = headers.get("X-TalentOS-Timestamp", "").strip()
    signature = headers.get("X-TalentOS-Signature", "").strip()
    if not signature:
        raise InvalidSignatureError()
    if not key_id or not raw_event_id or not timestamp:
        raise InvalidEnvelopeError()
    try:
        event_id = uuid.UUID(raw_event_id)
    except (TypeError, ValueError):
        raise InvalidEnvelopeError() from None
    return WebhookHeaders(
        key_id=key_id, event_id=event_id, timestamp=timestamp, signature=signature
    )


def parse_timestamp(value: str) -> datetime:
    """Acepta ISO 8601 en UTC (`Z` o `+00:00`); rechaza relojes no UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise StaleEventError() from None
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset != timedelta(0):
        raise StaleEventError()
    return parsed.astimezone(UTC)


def validate_timestamp(
    value: str, tolerance_seconds: int, *, now: datetime | None = None
) -> datetime:
    """Rechaza timestamps expirados y futuros fuera de la tolerancia."""
    timestamp = parse_timestamp(value)
    current = datetime.now(UTC) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise StaleEventError()
    delta = abs((current.astimezone(UTC) - timestamp).total_seconds())
    if delta > tolerance_seconds:
        raise StaleEventError()
    return timestamp


def verify_signature(signature: str, raw_body: bytes, secret: str) -> None:
    """HMAC-SHA256 sobre el cuerpo crudo con comparación en tiempo constante."""
    if not signature.startswith(_SIGNATURE_PREFIX):
        raise InvalidSignatureError()
    provided = signature[len(_SIGNATURE_PREFIX) :].strip().lower()
    try:
        bytes.fromhex(provided)
    except ValueError:
        raise InvalidSignatureError() from None
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise InvalidSignatureError()


def read_inbound_config(integration: Integration) -> WebhookInboundConfig:
    """Descifra y valida la config; tolerancia ausente usa 300 s."""
    if integration.provider is not IntegrationProvider.WEBHOOK_INBOUND:
        raise IntegrationTenantMismatchError()
    raw = decrypt_config(integration.encrypted_config_ref)
    candidate = {
        "secret": raw.get("secret"),
        "tolerance_seconds": raw.get("tolerance_seconds", 300),
    }
    try:
        return WebhookInboundConfig.model_validate(candidate)
    except ValidationError:
        raise IntegrationConfigUnreadableError() from None


def parse_envelope(
    raw_body: bytes, *, expected_event_id: uuid.UUID, expected_organization_id: uuid.UUID
) -> WebhookEnvelope:
    """Valida envelope estricto y comprueba event_id/tenant sin efectos."""
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise InvalidEnvelopeError() from None
    try:
        envelope = WebhookEnvelope.model_validate(decoded)
    except ValidationError:
        raise InvalidEnvelopeError() from None
    if (
        envelope.event_id != expected_event_id
        or envelope.organization_id != expected_organization_id
    ):
        raise InvalidEnvelopeError()
    return envelope


def canonical_payload_hash(payload: Mapping[str, object]) -> str:
    """SHA-256 del payload saneado y canónico; no guarda el payload."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_webhook_request(
    *,
    integration: Integration,
    raw_body: bytes,
    headers: Mapping[str, str],
    now: datetime | None = None,
) -> VerifiedWebhook:
    """Orquesta clave, config, tiempo, firma y envelope sobre la fila auténtica."""
    parsed = parse_headers(headers)
    if parsed.key_id != integration.key_id:
        raise UnknownKeyIdError()
    config = read_inbound_config(integration)
    validate_timestamp(parsed.timestamp, config.tolerance_seconds, now=now)
    verify_signature(parsed.signature, raw_body, config.secret)
    envelope = parse_envelope(
        raw_body,
        expected_event_id=parsed.event_id,
        expected_organization_id=integration.organization_id,
    )
    return VerifiedWebhook(
        envelope=envelope, payload_hash=canonical_payload_hash(envelope.payload)
    )


__all__ = [
    "DuplicateEventError",
    "InvalidEnvelopeError",
    "InvalidSignatureError",
    "StaleEventError",
    "UnknownKeyIdError",
    "WebhookDomainError",
    "WebhookHeaders",
    "WebhookRetryError",
    "VerifiedWebhook",
    "canonical_payload_hash",
    "parse_envelope",
    "parse_headers",
    "parse_timestamp",
    "read_inbound_config",
    "validate_timestamp",
    "verify_signature",
    "verify_webhook_request",
]
