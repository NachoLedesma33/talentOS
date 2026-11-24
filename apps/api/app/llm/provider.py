from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ProviderError(Exception):
    """Fallo de proveedor con código estable; nunca transporta payload ni credenciales."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@runtime_checkable
class LLMProvider(Protocol):
    """Contrato único de modelos; dominio y agentes no conocen proveedores concretos."""

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        """Devuelve un dict sin validar; el llamador lo valida con `schema`."""
        ...

    def generate_text(
        self,
        prompt_version: str,
        context: Mapping[str, object],
    ) -> str:
        """Texto libre del modelo; no se usa para decisiones de dominio."""
        ...

    def health_check(self) -> bool:
        """Comprueba disponibilidad sin enviar datos de candidatos."""
        ...

    def estimate_usage(
        self,
        prompt_version: str,
        context: Mapping[str, object],
    ) -> dict[str, int]:
        """Estimación de tokens; nunca incluye texto ni metadatos personales."""
        ...
