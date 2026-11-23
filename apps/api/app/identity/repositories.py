from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.identity.models import Membership, User


def get_user_by_email(db: DBSession, email: str, organization_id: uuid.UUID) -> User | None:
    """Busca un usuario por email SOLO dentro de la organización autenticada."""
    stmt = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            User.email == email.strip().lower(),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def get_membership(
    db: DBSession, user_id: uuid.UUID, organization_id: uuid.UUID
) -> Membership | None:
    """Devuelve la membresía exacta para el par usuario/organización."""
    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.organization_id == organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def user_belongs_to_organization(
    db: DBSession, user_id: uuid.UUID, organization_id: uuid.UUID
) -> bool:
    """Comprueba membresía; `organization_id` debe venir del contexto autenticado."""
    return get_membership(db, user_id, organization_id) is not None


def list_organization_members(db: DBSession, organization_id: uuid.UUID) -> list[Membership]:
    """Lista solo las membresías de la organización indicada."""
    stmt = (
        select(Membership)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at)
    )
    return list(db.execute(stmt).scalars().all())
