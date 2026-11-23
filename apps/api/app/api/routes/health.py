from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings, missing_required_settings

router = APIRouter(tags=["health"])

_READINESS_LIMITATION = (
    "Limitación de esta fase: /ready solo valida configuración; "
    "aún no comprueba conexiones reales a PostgreSQL ni Redis."
)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["talentos"]
    version: str


class ReadyResponse(HealthResponse):
    detail: str = _READINESS_LIMITATION


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", service="talentos", version="0.1.0")


@router.get("/ready", response_model=ReadyResponse)
def get_readiness(settings: Annotated[Settings, Depends(get_settings)]) -> ReadyResponse:
    missing = missing_required_settings(settings)
    if missing:
        detail = (
            "Configuración mínima incompleta: faltan o están vacías "
            + ", ".join(missing)
            + ". Defina esas variables en el entorno antes de iniciar la API. "
            + _READINESS_LIMITATION
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    return ReadyResponse(status="ok", service="talentos", version="0.1.0")
