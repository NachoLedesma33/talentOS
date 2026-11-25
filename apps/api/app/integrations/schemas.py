from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.agents.models import UnsafeAgentPayloadError
from app.agents.schemas import validate_safe_payload
from app.integrations.models import (
    EmailApprovalStatus,
    EmailDeliveryStatus,
    EmailLanguage,
    EmailTemplate,
    Integration,
    IntegrationProvider,
    IntegrationStatus,
    WebhookDeliveryStatus,
    WebhookEventStatus,
    WebhookEventType,
)


class _StrictModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)


class EmailSandboxConfig(_StrictModel):
    """Proveedor sandbox: sin credenciales ni datos personales."""

    sink: Literal["local_log"]


class WebhookOutboundConfig(_StrictModel):
    """Endpoint y secreto rotatorio; el envío queda fuera de esta unidad."""

    endpoint: HttpUrl
    secret: str = Field(min_length=16, max_length=256)


class WebhookInboundConfig(_StrictModel):
    """Secreto de firma y ventana anti-replay para recepción entrante."""

    secret: str = Field(min_length=16, max_length=256)
    tolerance_seconds: int = Field(ge=60, le=3600)


IntegrationConfig = EmailSandboxConfig | WebhookOutboundConfig | WebhookInboundConfig

_CONFIG_TYPES: dict[IntegrationProvider, type[_StrictModel]] = {
    IntegrationProvider.EMAIL_SANDBOX: EmailSandboxConfig,
    IntegrationProvider.WEBHOOK_OUTBOUND: WebhookOutboundConfig,
    IntegrationProvider.WEBHOOK_INBOUND: WebhookInboundConfig,
}


def _provider_for_config(config: IntegrationConfig) -> IntegrationProvider:
    if isinstance(config, EmailSandboxConfig):
        return IntegrationProvider.EMAIL_SANDBOX
    if isinstance(config, WebhookOutboundConfig):
        return IntegrationProvider.WEBHOOK_OUTBOUND
    return IntegrationProvider.WEBHOOK_INBOUND


def config_matches_provider(
    config: IntegrationConfig, provider: IntegrationProvider
) -> bool:
    """Comprueba que la forma del config corresponde al proveedor de la fila."""
    return isinstance(config, _CONFIG_TYPES[provider])


class IntegrationCreateRequest(_StrictModel):
    """Alta de un proveedor con configuración esquemática por proveedor."""

    provider: IntegrationProvider = Field(strict=False)
    config: IntegrationConfig

    @model_validator(mode="after")
    def _config_matches_provider(self) -> IntegrationCreateRequest:
        expected = _CONFIG_TYPES[self.provider]
        if not isinstance(self.config, expected):
            raise ValueError("Configuración incompatible con el proveedor")
        return self


class IntegrationUpdateRequest(_StrictModel):
    """Cambio de config o estado con control optimista de versión."""

    config: IntegrationConfig | None = None
    status: IntegrationStatus | None = Field(default=None, strict=False)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _one_change(self) -> IntegrationUpdateRequest:
        if (self.config is None) == (self.status is None):
            raise ValueError("Enviar config o status, no ambos ni ninguno")
        if self.config is not None:
            provider = _provider_for_config(self.config)
            expected = _CONFIG_TYPES[provider]
            if not isinstance(self.config, expected):
                raise ValueError("Configuración incompatible con el proveedor")
        return self


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntegrationResponse(_ResponseModel):
    """Metadatos públicos: sin config, token, secreto ni organization_id."""

    id: uuid.UUID
    provider: IntegrationProvider
    status: IntegrationStatus
    config_version: int
    key_id: str
    created_at: datetime
    updated_at: datetime


class IntegrationListResponse(_ResponseModel):
    items: list[IntegrationResponse]
    total: int
    limit: int
    offset: int


def safe_integration_metadata(integration: Integration) -> dict[str, object]:
    """Metadatos saneados para auditoría; nunca config, token ni secreto."""
    return validate_safe_payload(
        {
            "provider": str(integration.provider.value),
            "status": str(integration.status.value),
            "config_version": integration.config_version,
            "key_id": integration.key_id,
        }
    )


_MAX_WEBHOOK_PAYLOAD_KEYS = 50
_MAX_WEBHOOK_PAYLOAD_BYTES = 16_384


class WebhookEnvelope(_StrictModel):
    """Envelope versionado y saneado; `organization_id` solo se compara."""

    # JSON entrega IDs y fechas como texto: conversión explícita, extra prohibido.
    event_id: uuid.UUID = Field(strict=False)
    event_type: WebhookEventType = Field(strict=False)
    organization_id: uuid.UUID = Field(strict=False)
    occurred_at: datetime = Field(strict=False)
    resource_id: uuid.UUID = Field(strict=False)
    correlation_id: uuid.UUID = Field(strict=False)
    payload_version: Literal["1"]
    payload: dict[str, object]

    @field_validator("occurred_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at debe ser UTC")
        return value.astimezone(UTC)

    @field_validator("payload")
    @classmethod
    def _sanitize_payload(cls, value: dict[str, object]) -> dict[str, object]:
        try:
            safe = validate_safe_payload(value)
        except UnsafeAgentPayloadError:
            raise ValueError("payload no apto para webhook") from None
        if len(safe) > _MAX_WEBHOOK_PAYLOAD_KEYS:
            raise ValueError("payload con demasiados campos")
        canonical = json.dumps(
            safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if len(canonical.encode("utf-8")) > _MAX_WEBHOOK_PAYLOAD_BYTES:
            raise ValueError("payload demasiado grande")
        return safe


class WebhookAcceptedResponse(_ResponseModel):
    """Resultado público de la recepción; sin payload, secreto ni firma."""

    event_id: uuid.UUID
    correlation_id: uuid.UUID
    status: WebhookEventStatus
    duplicate: bool


class WebhookEventSummary(_ResponseModel):
    """Estado diagnóstico de un evento; nunca incluye payload ni cabeceras."""

    id: uuid.UUID
    event_id: uuid.UUID
    event_type: WebhookEventType
    status: WebhookEventStatus
    attempts: int
    last_error_code: str | None
    occurred_at: datetime
    received_at: datetime


_OUTBOUND_MARKER_TOKENS = frozenset(
    {
        "api_key",
        "authorization",
        "correo",
        "cv",
        "curriculum",
        "e_mail",
        "email",
        "password",
        "personal_email",
        "phone",
        "resume",
        "secret",
        "token",
    }
)
_OUTBOUND_MARKER_VALUE = re.compile(
    r"(?i)(@|bearer\s+|sk-[a-z0-9]{8,}|api[_-]?key\s*[:=]|password\s*[:=]"
    r"|\bcv\b|curriculum|resume)"
)


def _reject_outbound_markers(value: object) -> None:
    """Rechaza marcadores de CV, correo, token o secreto en cualquier profundidad."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
            segments = set(normalized.split("_"))
            if normalized in _OUTBOUND_MARKER_TOKENS or segments & _OUTBOUND_MARKER_TOKENS:
                raise ValueError("payload con marcador sensible")
            _reject_outbound_markers(item)
        return
    if isinstance(value, str):
        if _OUTBOUND_MARKER_VALUE.search(value):
            raise ValueError("payload con marcador sensible")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_outbound_markers(item)


class OutboundEventRequest(_StrictModel):
    """Evento saliente: campos cerrados y payload mínimo, acotado y saneado."""

    event_id: uuid.UUID = Field(strict=False)
    event_type: WebhookEventType = Field(strict=False)
    resource_id: uuid.UUID = Field(strict=False)
    correlation_id: uuid.UUID = Field(strict=False)
    payload: dict[str, object]

    @field_validator("payload")
    @classmethod
    def _sanitize_outbound_payload(cls, value: dict[str, object]) -> dict[str, object]:
        try:
            safe = validate_safe_payload(value)
        except UnsafeAgentPayloadError:
            raise ValueError("payload no apto para webhook saliente") from None
        _reject_outbound_markers(safe)
        if len(safe) > _MAX_WEBHOOK_PAYLOAD_KEYS:
            raise ValueError("payload con demasiados campos")
        canonical = json.dumps(
            safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if len(canonical.encode("utf-8")) > _MAX_WEBHOOK_PAYLOAD_BYTES:
            raise ValueError("payload demasiado grande")
        return safe


class WebhookDeliverySummary(_ResponseModel):
    """Diagnóstico de entrega saliente; jamás incluye payload ni cuerpo."""

    id: uuid.UUID
    event_id: uuid.UUID
    event_type: WebhookEventType
    status: WebhookDeliveryStatus
    attempts: int
    last_error_code: str | None
    last_status_code: int | None
    created_at: datetime
    delivered_at: datetime | None


class WebhookDeliveryListResponse(_ResponseModel):
    """Listado paginado de entregas salientes del tenant."""

    items: list[WebhookDeliverySummary]
    total: int
    limit: int
    offset: int


_EMAIL_TEXT_MARKERS = re.compile(
    r"(?i)("
    r"\b(?:cv|curriculum|resume|correo|email|e_mail|phone|telefono|tel[eé]fono"
    r"|secret|secreto|token|password|clave|api[_-]?key|name|nombre"
    r"|recipient|destinatario)\b"
    r"|https?://|www\.|sk-[a-z0-9]{8,}|\d{7,}|@"
    r")"
)


class EmailDraftCreateRequest(_StrictModel):
    """Campos cerrados: sin email, nombre, CV, cuerpo, token ni destinatario."""

    candidate_id: uuid.UUID = Field(strict=False)
    template: EmailTemplate = Field(strict=False)
    topic: str = Field(min_length=1, max_length=120)
    language: EmailLanguage = Field(strict=False)
    call_to_action: str = Field(min_length=1, max_length=120)

    @field_validator("topic", "call_to_action")
    @classmethod
    def _reject_direct_pii(cls, value: str) -> str:
        _reject_outbound_markers(value)
        if _EMAIL_TEXT_MARKERS.search(value):
            raise ValueError("texto con dato personal o secreto")
        return value


class EmailDraftSummary(_ResponseModel):
    """Resumen del borrador; nunca incluye asunto, cuerpo ni hash."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    template: EmailTemplate
    approval_status: EmailApprovalStatus
    delivery_status: EmailDeliveryStatus
    attempts: int
    created_at: datetime


class EmailDraftDetail(EmailDraftSummary):
    """Detalle saneado: asunto y hash generados por servidor, sin cuerpo."""

    integration_id: uuid.UUID
    topic: str
    language: EmailLanguage
    call_to_action: str
    subject: str
    body_hash: str
    requested_by: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    last_error_code: str | None
    sent_at: datetime | None
    updated_at: datetime


class EmailDraftListResponse(_ResponseModel):
    items: list[EmailDraftSummary]
    total: int
    limit: int
    offset: int


__all__ = [
    "EmailDraftCreateRequest",
    "EmailDraftDetail",
    "EmailDraftListResponse",
    "EmailDraftSummary",
    "EmailSandboxConfig",
    "IntegrationConfig",
    "IntegrationCreateRequest",
    "IntegrationListResponse",
    "IntegrationResponse",
    "IntegrationUpdateRequest",
    "OutboundEventRequest",
    "WebhookAcceptedResponse",
    "WebhookDeliveryListResponse",
    "WebhookDeliverySummary",
    "WebhookEnvelope",
    "WebhookEventSummary",
    "WebhookInboundConfig",
    "WebhookOutboundConfig",
    "config_matches_provider",
    "safe_integration_metadata",
]
