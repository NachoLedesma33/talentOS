from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

_REQUIRED_SETTINGS = (
    "APP_ENV",
    "APP_NAME",
    "API_BASE_URL",
    "WEB_BASE_URL",
    "DATABASE_URL",
    "REDIS_URL",
    "LOG_LEVEL",
    "LLM_PROVIDER",
)


class Settings(BaseSettings):
    """Configuración del backend, cargada solo desde entorno."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_ENV: Literal["local", "test", "staging", "production"] = "local"
    APP_NAME: str = "TalentOS"
    API_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    WEB_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")
    # Valor local del SDD 17.2; no es una credencial real.
    DATABASE_URL: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://postgres:postgres@localhost:5432/talentos"
    )
    REDIS_URL: RedisDsn = RedisDsn("redis://localhost:6379/0")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LLM_PROVIDER: Literal["mock"] = "mock"
    SESSION_COOKIE_NAME: str = "talentos_session"
    SESSION_TTL_SECONDS: int = 86400


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración validada una sola vez por proceso."""
    return Settings()


def missing_required_settings(settings: Settings) -> list[str]:
    """Lista variables de configuración vacías; no comprueba servicios externos."""
    missing: list[str] = []
    for name in _REQUIRED_SETTINGS:
        value: object = getattr(settings, name)
        if value is None or not str(value).strip():
            missing.append(name)
    return missing
