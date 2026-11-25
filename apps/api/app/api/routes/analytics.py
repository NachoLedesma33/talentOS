"""API REST de métricas del proceso.

Router delgado: la organización se toma de la sesión autorizada, nunca del cliente.
El servicio de dominio calcula las métricas y declara qué dato es estimado.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.analytics.service import AnalyticsOverview, build_analytics_overview
from app.db.session import get_db
from app.identity.dependencies import get_current_organization, require_roles
from app.identity.models import Membership, MembershipRole, Organization

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

DbDependency = Annotated[DBSession, Depends(get_db)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
ReadMember = Annotated[
    Membership,
    Depends(require_roles(*tuple(MembershipRole))),
]


@router.get("/overview", response_model=AnalyticsOverview)
def get_overview(
    active_organization: CurrentOrganization,
    db: DbDependency,
    _member: ReadMember,
) -> AnalyticsOverview:
    """Devuelve el panorama del tenant activo; sin parámetros de organización."""
    return build_analytics_overview(db, active_organization.id)
