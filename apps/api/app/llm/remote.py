from __future__ import annotations

from collections.abc import Mapping

import httpx
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.llm.provider import LLMProvider, ProviderError


class RemoteLLMProvider(LLMProvider):
    """Adaptador HTTP configurable. Nunca registra clave, payload ni texto del CV."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        config = settings or get_settings()
        base_url = config.LLM_BASE_URL.strip()
        api_key = config.LLM_API_KEY.strip()
        if not base_url or not api_key:
            raise ProviderError(
                "provider_configuration",
                "remote provider requires LLM_BASE_URL and LLM_API_KEY",
            )
        self._model = config.LLM_MODEL.strip()
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=config.LLM_TIMEOUT_SECONDS,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            raise ProviderError("provider_timeout") from None
        except httpx.HTTPStatusError:
            raise ProviderError("provider_http_error") from None
        except httpx.RequestError:
            raise ProviderError("provider_unavailable") from None
        except ValueError:
            raise ProviderError("provider_invalid_response") from None
        if not isinstance(data, dict):
            raise ProviderError("provider_invalid_response")
        return data

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "prompt_version": prompt_version,
            "schema": schema.__name__,
            "context": context,
        }
        if self._model:
            payload["model"] = self._model
        return self._post("/v1/structured-output", payload)

    def generate_text(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> str:
        payload: dict[str, object] = {
            "prompt_version": prompt_version,
            "context": context,
        }
        if self._model:
            payload["model"] = self._model
        data = self._post("/v1/text", payload)
        text = data.get("text")
        if not isinstance(text, str):
            raise ProviderError("provider_invalid_response")
        return text

    def health_check(self) -> bool:
        try:
            response = self._client.get("/health")
            response.raise_for_status()
        except httpx.HTTPError:
            raise ProviderError("provider_unavailable") from None
        return True

    def estimate_usage(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> dict[str, int]:
        del prompt_version
        # Aproximación local: no envía el CV a ningún servicio ni expone su texto.
        pages = context.get("pages")
        chars = len(str(pages)) if pages is not None else 0
        return {"prompt_tokens": max(1, chars // 4), "completion_tokens": 0}
