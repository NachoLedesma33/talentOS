from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.agents.schemas import validate_safe_payload
from app.integrations.models import Integration, IntegrationProvider, IntegrationStatus


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
    """Secreto de firma y ventana anti-replay; sin procesar eventos todavía."""

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


__all__ = [
    "EmailSandboxConfig",
    "IntegrationConfig",
    "IntegrationCreateRequest",
    "IntegrationListResponse",
    "IntegrationResponse",
    "IntegrationUpdateRequest",
    "WebhookInboundConfig",
    "WebhookOutboundConfig",
    "config_matches_provider",
    "safe_integration_metadata",
]
