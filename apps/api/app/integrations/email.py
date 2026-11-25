"""Puerto de envío de correo y adaptador sandbox sin red ni datos personales.

El adaptador no conoce base de datos, organizaciones, candidatos ni reglas de
negocio: recibe un mensaje ya saneado y devuelve solo una referencia opaca o un
código de error estable. Nunca imprime ni registra asunto, cuerpo ni correo.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.logging import log_structured

_SINK = "local_log"
_REF_PREFIX = "sandbox:"
_REF_BYTES = 16


@dataclass(frozen=True)
class EmailMessage:
    """Contenido mínimo en memoria; el texto es generado por el servidor."""

    candidate_id: uuid.UUID
    subject: str
    text: str


@dataclass(frozen=True)
class EmailDeliveryResult:
    """Resultado observable: referencia opaca o código de error estable."""

    ref: str | None
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.ref)


@runtime_checkable
class EmailSender(Protocol):
    """Puerto de envío; las implementaciones no conocen tenants ni entidades."""

    def send(self, message: EmailMessage) -> EmailDeliveryResult: ...


class SandboxEmailSender:
    """Sumidero determinista `local_log`: sin SMTP, red ni texto en logs."""

    sink: str = _SINK

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        canonical = f"{message.candidate_id}\n{message.subject}\n{message.text}"
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_REF_BYTES]
        ref = f"{_REF_PREFIX}{digest}"
        # Solo IDs y hash: ni asunto, ni cuerpo, ni datos de contacto.
        log_structured(
            logging.INFO,
            f"email.sandbox.dispatched ref={ref} candidate_id={message.candidate_id}",
        )
        return EmailDeliveryResult(ref)


class StubEmailSender:
    """Sender determinista de tests: resultados en cola y mensajes capturados."""

    def __init__(self, results: Sequence[EmailDeliveryResult] = ()) -> None:
        self._results = list(results)
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        self.messages.append(message)
        if self._results:
            return self._results.pop(0)
        return EmailDeliveryResult(f"{_REF_PREFIX}stub-{len(self.messages):04d}")


__all__ = [
    "EmailDeliveryResult",
    "EmailMessage",
    "EmailSender",
    "SandboxEmailSender",
    "StubEmailSender",
]
