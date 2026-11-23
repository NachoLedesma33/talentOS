from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.core import config
from app.identity.models import Session as UserSession
from app.identity.models import User, UserStatus
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
