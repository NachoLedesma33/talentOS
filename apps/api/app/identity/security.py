from __future__ import annotations

import hashlib
import secrets

import bcrypt

# bcrypt solo consume los primeros 72 bytes: rechazar evita truncamiento silencioso.
MAX_PASSWORD_BYTES = 72


def _password_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("La contraseña supera el máximo admitido por bcrypt.")
    return encoded


def hash_password(password: str) -> str:
    """Devuelve un hash bcrypt con sal; la contraseña nunca se persiste."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Comprueba la contraseña sin registrar su valor ni el hash en logs."""
    try:
        candidate = _password_bytes(password)
        stored = password_hash.encode("ascii")
    except (TypeError, UnicodeError, ValueError):
        return False
    try:
        return bcrypt.checkpw(candidate, stored)
    except (TypeError, ValueError):
        return False


def new_session_token() -> str:
    """Token opaco de 256 bits de entropía; solo se devuelve al cliente."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Huella SHA-256 del token: lo que se guarda en la base de datos."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
