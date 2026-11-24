"""Cifrado simétrico de la configuración sensible de integraciones.

Fernet (AEAD) evita implementar cifrado casero. La clave se lee solo de
`Settings.INTEGRATION_ENCRYPTION_KEY`; nunca se registra ni se devuelve.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from typing import cast

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.integrations.models import (
    IntegrationConfigUnreadableError,
    IntegrationKeyMissingError,
)


def _key_material() -> tuple[str, bytes]:
    """Devuelve (clave base64, bytes decodificados) o un error determinista."""
    raw = get_settings().INTEGRATION_ENCRYPTION_KEY.strip()
    if not raw:
        raise IntegrationKeyMissingError()
    try:
        Fernet(raw.encode("ascii"))
        material = base64.urlsafe_b64decode(raw.encode("ascii"))
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise IntegrationKeyMissingError() from None
    if len(material) != 32:
        raise IntegrationKeyMissingError()
    return raw, material


def current_key_id() -> str:
    """Identificador público de la clave: sha256(bytes).hexdigest()[:12]."""
    return hashlib.sha256(_key_material()[1]).hexdigest()[:12]


def encrypt_config(config: Mapping[str, object]) -> tuple[str, str]:
    """Cifra la configuración canónica; devuelve (token, key_id)."""
    raw, material = _key_material()
    canonical = json.dumps(
        config, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    token = Fernet(raw.encode("ascii")).encrypt(canonical.encode("utf-8"))
    key_id = hashlib.sha256(material).hexdigest()[:12]
    return token.decode("ascii"), key_id


def decrypt_config(token: str) -> dict[str, object]:
    """Descifra y valida la forma del payload; errores sin datos del token."""
    raw, _material = _key_material()
    try:
        plaintext = Fernet(raw.encode("ascii")).decrypt(token.encode("ascii"))
        decoded: object = json.loads(plaintext.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        raise IntegrationConfigUnreadableError() from None
    if not isinstance(decoded, dict):
        raise IntegrationConfigUnreadableError()
    return cast(dict[str, object], decoded)
