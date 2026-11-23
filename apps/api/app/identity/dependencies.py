"""Dependencias de identidad, organización activa y matriz mínima de roles.

Matriz de esta unidad (sin matrices genéricas):

- ``owner``: todo; crear organización, invitar, cambiar roles y configuración.
- ``admin``: invitar y cambiar roles no-owner, configuración operativa; no puede
  degradar al último owner ni asignar/quitar el rol ``owner``.
- ``recruiter``: recursos de reclutamiento (vacantes/candidatos); aún sin endpoints
  en esta unidad; no administra miembros.
- ``reviewer``: lectura y aprobaciones; no invita ni cambia roles.
- ``viewer``: solo lectura de recursos autorizados.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core import config
from app.db.session import get_db
from app.identity.models import Membership, MembershipRole, Organization, User, UserStatus
from app.identity.models import Session as UserSession
from app.identity.repositories import get_membership
from app.identity.security import hash_token

_UNAUTHORIZED_MESSAGE = "Autenticación requerida."
_FORBIDDEN_MESSAGE = "Origen no permitido."
_ROLE_MESSAGE = "Rol insuficiente."
_ORGANIZATION_MESSAGE = "Organización no disponible."
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

DbDependency = Annotated[DBSession, Depends(get_db)]


def _utc(value: datetime) -> datetime:
    """SQLite puede devolver datetimes naive; normalizar antes de comparar."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_current_user(request: Request, db: DbDependency) -> User:
    """Resuelve la cookie de sesión; nunca lee organization_id del cliente."""
    settings = config.get_settings()
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_MESSAGE)

    token_hash = hash_token(token)
    session = db.execute(
        select(UserSession).where(UserSession.token_hash == token_hash)
    ).scalar_one_or_none()
    if (
        session is None
        or session.revoked_at is not None
        or _utc(session.expires_at) <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_MESSAGE)

    user = db.get(User, session.user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_MESSAGE)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_organization(
    request: Request,
    user: CurrentUser,
    db: DbDependency,
) -> Organization:
    """Resuelve la org activa solo si el usuario autenticado tiene membresía."""
    raw_organization_id = request.headers.get("X-Organization-ID")
    if not raw_organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ORGANIZATION_MESSAGE)
    try:
        organization_id = uuid.UUID(raw_organization_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_ORGANIZATION_MESSAGE
        ) from None

    membership = get_membership(db, user.id, organization_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ORGANIZATION_MESSAGE)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ORGANIZATION_MESSAGE)

    request.state.organization_id = str(organization.id)
    return organization


CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]


def require_roles(*roles: MembershipRole) -> Callable[..., Membership]:
    """Devuelve una dependencia que exige uno de los roles en la org activa."""
    allowed = frozenset(roles)

    def _require_roles(
        user: CurrentUser,
        organization: CurrentOrganization,
        db: DbDependency,
    ) -> Membership:
        membership = get_membership(db, user.id, organization.id)
        if membership is None or membership.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ROLE_MESSAGE)
        return membership

    return _require_roles


def _origin_key(url: str) -> tuple[str, str] | None:
    """Esquema + host con puerto efectivo; `None` para valores inutilizables."""
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.lower(), f"{parsed.hostname.lower()}:{port}"


def verify_origin(request: Request) -> None:
    """Defensa CSRF para métodos mutantes cuando el cliente envía Origin."""
    if request.method not in _MUTATING_METHODS:
        return
    origin = request.headers.get("origin")
    if not origin:
        return

    settings = config.get_settings()
    allowed: set[tuple[str, str]] = set()
    for base in (settings.WEB_BASE_URL, settings.API_BASE_URL):
        key = _origin_key(str(base))
        if key is not None:
            allowed.add(key)

    if _origin_key(origin) not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_MESSAGE)
