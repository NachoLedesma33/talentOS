from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.agents.models import UnsafeAgentPayloadError
from app.agents.schemas import validate_safe_payload
from app.integrations.models import (
    Integration,
    IntegrationProvider,
    IntegrationStatus,
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


__all__ = [
    "EmailSandboxConfig",
    "IntegrationConfig",
    "IntegrationCreateRequest",
    "IntegrationListResponse",
    "IntegrationResponse",
    "IntegrationUpdateRequest",
    "WebhookAcceptedResponse",
    "WebhookEnvelope",
    "WebhookEventSummary",
    "WebhookInboundConfig",
    "WebhookOutboundConfig",
    "config_matches_provider",
    "safe_integration_metadata",
]
