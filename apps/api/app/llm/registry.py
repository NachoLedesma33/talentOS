from __future__ import annotations

from app.core.config import Settings, get_settings
from app.llm.mock import MockLLMProvider
from app.llm.provider import LLMProvider, ProviderError
from app.llm.remote import RemoteLLMProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Selecciona el proveedor por configuración; sin caché para respetar cambios de entorno."""
    config = settings or get_settings()
    if config.LLM_PROVIDER == "mock":
        return MockLLMProvider()
    if config.LLM_PROVIDER == "remote":
        return RemoteLLMProvider(config)
    # `Literal` ya bloquea otros valores; mensaje sin valores ni credenciales.
    raise ProviderError("provider_configuration", "unsupported LLM_PROVIDER")
