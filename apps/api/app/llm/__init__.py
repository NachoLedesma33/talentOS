"""Capa de proveedores LLM: interfaz, mock determinista y adaptador remoto."""

from app.llm.provider import LLMProvider, ProviderError

__all__ = ["LLMProvider", "ProviderError"]
