from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings

# Valor efímero por proceso: no se persiste, no se envía y no añade variables de entorno.
# Las URLs firmadas dejan de ser válidas al reiniciar el proceso (duran solo 60 s).
_PROCESS_KEY = secrets.token_bytes(32)
_DEFAULT_TTL_SECONDS = 60


def _now() -> datetime:
    return datetime.now(UTC)


def _signing_key() -> bytes:
    """Deriva la clave de sesión del nombre de cookie y el valor en memoria del proceso."""
    cookie_name = get_settings().SESSION_COOKIE_NAME
    return hashlib.sha256(cookie_name.encode("utf-8") + b"\x00" + _PROCESS_KEY).digest()


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )


def create_download_token(
    *,
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Devuelve token firmado y su expiración; el payload solo lleva IDs y `exp`."""
    expires_at = (now or _now()) + timedelta(seconds=ttl_seconds)
    payload: dict[str, str | int] = {
        "document_id": str(document_id),
        "organization_id": str(organization_id),
        "exp": int(expires_at.timestamp()),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    segment = _encode(raw)
    signature = hmac.new(_signing_key(), segment.encode("ascii"), hashlib.sha256).digest()
    return f"{segment}.{_encode(signature)}", expires_at


def verify_download_token(
    token: str,
    *,
    organization_id: uuid.UUID,
    now: datetime | None = None,
) -> uuid.UUID | None:
    """Valida firma, expiración y tenant; devuelve solo el document_id autorizado."""
    try:
        payload_segment, signature_segment = token.split(".", 1)
        expected = hmac.new(
            _signing_key(), payload_segment.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_decode(signature_segment), expected):
            return None

        decoded = json.loads(_decode(payload_segment))
        if not isinstance(decoded, dict):
            return None
        document_value = decoded.get("document_id")
        organization_value = decoded.get("organization_id")
        expiration = decoded.get("exp")
        if (
            not isinstance(document_value, str)
            or not isinstance(organization_value, str)
            or not isinstance(expiration, int)
            or isinstance(expiration, bool)
        ):
            return None
        if uuid.UUID(organization_value) != organization_id:
            return None
        if expiration <= int((now or _now()).timestamp()):
            return None
        return uuid.UUID(document_value)
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return None
