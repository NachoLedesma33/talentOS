"""Adaptador de envío de webhooks salientes, sin dominio ni base de datos.

La interfaz recibe ya construidos el endpoint, las cabeceras y el cuerpo firmado.
Solo devuelve el código HTTP y un código de error estable: nunca guarda el cuerpo,
la respuesta completa, secretos ni datos de candidatos.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

_TIMEOUT_SECONDS = 5.0
_CODE_TIMEOUT = "provider_timeout"
_CODE_REJECTED = "provider_rejected"


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Resultado mínimo observable de un intento de entrega."""

    status_code: int | None
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


@runtime_checkable
class WebhookSender(Protocol):
    """Puerto de envío; las implementaciones no conocen tenants ni entidades."""

    def send(
        self, endpoint: str, headers: Mapping[str, str], body: bytes
    ) -> WebhookDeliveryResult: ...


class HttpxWebhookSender:
    """Adaptador real con timeout fijo; una conexión por intento."""

    def __init__(self, timeout: float = _TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def send(
        self, endpoint: str, headers: Mapping[str, str], body: bytes
    ) -> WebhookDeliveryResult:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(endpoint, content=body, headers=dict(headers))
        except (httpx.TimeoutException, httpx.RequestError):
            return WebhookDeliveryResult(None, _CODE_TIMEOUT)
        status_code = response.status_code
        error_code = None if 200 <= status_code < 300 else _CODE_REJECTED
        return WebhookDeliveryResult(status_code, error_code)


@dataclass(frozen=True)
class StubCall:
    """Evidencia en memoria de un envío; solo para pruebas deterministas."""

    endpoint: str
    headers: dict[str, str]
    body: bytes


class StubWebhookSender:
    """Sender determinista: devuelve resultados en cola, sin red."""

    def __init__(self, results: Sequence[WebhookDeliveryResult] = ()) -> None:
        self._results = list(results)
        self.calls: list[StubCall] = []

    def send(
        self, endpoint: str, headers: Mapping[str, str], body: bytes
    ) -> WebhookDeliveryResult:
        self.calls.append(StubCall(endpoint, dict(headers), body))
        if self._results:
            return self._results.pop(0)
        return WebhookDeliveryResult(200, None)


__all__ = [
    "HttpxWebhookSender",
    "StubCall",
    "StubWebhookSender",
    "WebhookDeliveryResult",
    "WebhookSender",
]
