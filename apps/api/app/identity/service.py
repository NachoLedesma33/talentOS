from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.audit.service import record_audit
from app.core import config
from app.identity.models import Membership, MembershipRole, Organization, User, UserStatus
from app.identity.models import Session as UserSession
from app.identity.repositories import get_membership, list_organization_members
from app.identity.schemas import MemberResponse
from app.identity.security import hash_password, hash_token, new_session_token, verify_password


class EmailAlreadyRegisteredError(Exception):
    """El email ya pertenece a un usuario."""


class InvalidCredentialsError(Exception):
    """Credenciales o sesión no válidas; mensaje público genérico."""


def _find_user_by_email(db: DBSession, email: str) -> User | None:
    # Registro/login son pre-autenticación: aún no existe contexto de organización.
    # El filtro por memberships se incorpora con la selección de organización activa.
    stmt = select(User).where(User.email == email.strip().lower())
    return db.execute(stmt).scalar_one_or_none()


def register_user(db: DBSession, *, email: str, password: str, name: str) -> User:
    """Crea un usuario activo; no inicia sesión ni crea organización."""
    normalized_email = email.strip().lower()
    if _find_user_by_email(db, normalized_email) is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        name=name.strip(),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegisteredError from None
    return user


def authenticate_user(db: DBSession, *, email: str, password: str) -> tuple[User, str]:
    """Devuelve el usuario y un token nuevo; guarda solo su huella."""
    user = _find_user_by_email(db, email)
    if (
        user is None
        or user.status is not UserStatus.ACTIVE
        or not verify_password(password, user.password_hash)
    ):
        raise InvalidCredentialsError

    settings = config.get_settings()
    token = new_session_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.SESSION_TTL_SECONDS),
    )
    db.add(session)
    db.commit()
    return user, token


def revoke_session(db: DBSession, *, user: User, token: str) -> None:
    """Revoca la sesión autenticada si sigue vigente; logout idempotente."""
    stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.token_hash == hash_token(token),
        UserSession.revoked_at.is_(None),
    )
    session = db.execute(stmt).scalar_one_or_none()
    if session is None:
        return
    session.revoked_at = datetime.now(UTC)
    db.commit()


class OrganizationSlugAlreadyExistsError(Exception):
    """El slug de organización ya está tomado."""


class OrganizationAccessError(Exception):
    """El recurso pedido no pertenece a la organización activa."""


class InsufficientRoleError(Exception):
    """El actor no tiene rol para la operación de dominio."""


class InvitedUserNotFoundError(Exception):
    """No existe usuario con el email indicado."""


class MemberAlreadyExistsError(Exception):
    """El usuario ya pertenece a la organización."""


class MemberNotFoundError(Exception):
    """El usuario objetivo no es miembro de la organización activa."""


class CannotInviteSelfError(Exception):
    """El actor ya es miembro: no puede invitarse a sí mismo."""


class RoleAssignmentForbiddenError(Exception):
    """Solo owner puede asignar o quitar el rol owner."""


class LastOwnerError(Exception):
    """La organización no puede quedarse sin owner."""


class RoleUnchangedError(Exception):
    """El miembro ya tiene el rol solicitado."""


def _assert_active_organization(
    active_organization_id: uuid.UUID, requested_organization_id: uuid.UUID
) -> None:
    if active_organization_id != requested_organization_id:
        raise OrganizationAccessError


def _require_actor_role(
    db: DBSession,
    actor: User,
    organization_id: uuid.UUID,
    allowed: frozenset[MembershipRole],
) -> Membership:
    membership = get_membership(db, actor.id, organization_id)
    if membership is None or membership.role not in allowed:
        raise InsufficientRoleError
    return membership


def _member_response(membership: Membership, user: User) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role,
    )


def create_organization(db: DBSession, *, creator: User, name: str, slug: str) -> Organization:
    """Crea la organización con su creador como owner y deja auditoría."""
    organization = Organization(name=name.strip(), slug=slug.strip().lower())
    db.add(organization)
    try:
        db.flush()
        db.add(
            Membership(
                organization_id=organization.id,
                user_id=creator.id,
                role=MembershipRole.OWNER,
            )
        )
        record_audit(
            db,
            organization_id=organization.id,
            actor_id=creator.id,
            action="organization.created",
            resource_type="organization",
            resource_id=organization.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise OrganizationSlugAlreadyExistsError from None
    return organization


def list_user_organizations(db: DBSession, *, user_id: uuid.UUID) -> list[Organization]:
    """Devuelve solo organizaciones donde el usuario tiene membresía."""
    stmt = (
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name)
    )
    return list(db.execute(stmt).scalars().all())


def list_members(
    db: DBSession, *, active_organization_id: uuid.UUID, requested_organization_id: uuid.UUID
) -> list[MemberResponse]:
    """Lista miembros de la organización activa; ignora el ID pedido si difiere."""
    _assert_active_organization(active_organization_id, requested_organization_id)
    memberships = list_organization_members(db, active_organization_id)
    result: list[MemberResponse] = []
    for membership in memberships:
        user = db.get(User, membership.user_id)
        if user is not None:
            result.append(_member_response(membership, user))
    return result


def invite_member(
    db: DBSession,
    *,
    actor: User,
    active_organization_id: uuid.UUID,
    requested_organization_id: uuid.UUID,
    email: str,
    role: MembershipRole,
) -> MemberResponse:
    """Invita a un usuario existente; solo owner/admin y sin escalado a owner."""
    _assert_active_organization(active_organization_id, requested_organization_id)
    actor_membership = _require_actor_role(
        db, actor, active_organization_id, frozenset({MembershipRole.OWNER, MembershipRole.ADMIN})
    )
    normalized_email = email.strip().lower()
    invited_user = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if invited_user is None:
        raise InvitedUserNotFoundError
    if invited_user.id == actor.id:
        raise CannotInviteSelfError
    if get_membership(db, invited_user.id, active_organization_id) is not None:
        raise MemberAlreadyExistsError
    if role is MembershipRole.OWNER and actor_membership.role is not MembershipRole.OWNER:
        raise RoleAssignmentForbiddenError

    membership = Membership(
        organization_id=active_organization_id,
        user_id=invited_user.id,
        role=role,
    )
    db.add(membership)
    try:
        db.flush()
        record_audit(
            db,
            organization_id=active_organization_id,
            actor_id=actor.id,
            action="member.invited",
            resource_type="membership",
            resource_id=membership.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise MemberAlreadyExistsError from None
    return _member_response(membership, invited_user)


def change_member_role(
    db: DBSession,
    *,
    actor: User,
    active_organization_id: uuid.UUID,
    requested_organization_id: uuid.UUID,
    user_id: uuid.UUID,
    new_role: MembershipRole,
) -> MemberResponse:
    """Cambia el rol de un miembro; nunca deja la organización sin owner."""
    _assert_active_organization(active_organization_id, requested_organization_id)
    actor_membership = _require_actor_role(
        db, actor, active_organization_id, frozenset({MembershipRole.OWNER, MembershipRole.ADMIN})
    )
    target = get_membership(db, user_id, active_organization_id)
    if target is None:
        raise MemberNotFoundError
    if target.role is new_role:
        raise RoleUnchangedError
    if new_role is MembershipRole.OWNER and actor_membership.role is not MembershipRole.OWNER:
        raise RoleAssignmentForbiddenError
    if target.role is MembershipRole.OWNER:
        owners = db.scalars(
            select(Membership).where(
                Membership.organization_id == active_organization_id,
                Membership.role == MembershipRole.OWNER,
            )
        ).all()
        if len(owners) <= 1:
            raise LastOwnerError

    target.role = new_role
    db.flush()
    record_audit(
        db,
        organization_id=active_organization_id,
        actor_id=actor.id,
        action="member.role_changed",
        resource_type="membership",
        resource_id=target.id,
    )
    db.commit()
    user = db.get(User, user_id)
    if user is None:
        raise MemberNotFoundError
    return _member_response(target, user)

