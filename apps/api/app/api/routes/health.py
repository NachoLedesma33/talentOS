from __future__ import annotations

import socket
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings, missing_required_settings
from app.db.session import engine

router = APIRouter(tags=["health"])

DependencyStatus = Literal["ok", "error", "skipped"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["talentos"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyStatus]
    detail: str | None = None


def _check_database() -> bool:
    """Comprueba PostgreSQL con una consulta mínima; nunca devuelve el error del driver."""
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        return False
    return True


def _redis_target(settings: Settings) -> tuple[str, int]:
    """Extrae host y puerto del DSN sin exponerlo."""
    parsed = urlparse(str(settings.REDIS_URL))
    return parsed.hostname or "localhost", parsed.port or 6379


def _check_redis(settings: Settings) -> bool:
    """Comprueba Redis por TCP en 1 s sin devolver credenciales ni ruta."""
    host, port = _redis_target(settings)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", service="talentos", version="0.1.0")


@router.get("/ready", response_model=ReadyResponse, response_model_exclude_none=True)
def get_readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadyResponse | JSONResponse:
    missing = missing_required_settings(settings)
    if missing:
        payload = ReadyResponse(
            status="not_ready",
            dependencies={"database": "skipped", "redis": "skipped"},
            detail=(
                "Configuración mínima incompleta: faltan o están vacías "
                + ", ".join(missing)
                + ". No se comprobaron PostgreSQL ni Redis."
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(exclude_none=True),
        )

    dependencies: dict[str, DependencyStatus] = {
        "database": "ok" if _check_database() else "error",
        "redis": "ok" if _check_redis(settings) else "error",
    }
    failed = [name for name, value in dependencies.items() if value != "ok"]
    if failed:
        payload = ReadyResponse(
            status="not_ready",
            dependencies=dependencies,
            detail="Dependencias no disponibles: " + ", ".join(failed) + ".",
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(exclude_none=True),
        )

    return ReadyResponse(status="ready", dependencies=dependencies)
