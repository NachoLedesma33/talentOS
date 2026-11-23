from __future__ import annotations

import os
import re
from enum import StrEnum
from pathlib import Path
from uuid import UUID

_INTERNAL_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,100}\.(?:pdf|docx)")


class StorageErrorCode(StrEnum):
    INVALID_KEY = "invalid_storage_key"
    UNAVAILABLE = "storage_unavailable"


class DocumentStorageError(Exception):
    """Fallo de storage: código estable, nunca ruta absoluta ni detalle del archivo."""

    def __init__(self, code: StorageErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def _base_dir() -> Path:
    """Raíz privada bajo `apps/api/var/documents`, derivada del paquete `app`."""
    return Path(__file__).resolve().parents[2] / "var" / "documents"


def _key_path(organization_id: object, document_id: object, internal_name: str) -> Path:
    if not isinstance(organization_id, UUID) or not isinstance(document_id, UUID):
        raise DocumentStorageError(StorageErrorCode.INVALID_KEY)
    if _INTERNAL_NAME_RE.fullmatch(internal_name) is None:
        raise DocumentStorageError(StorageErrorCode.INVALID_KEY)
    return _base_dir() / str(organization_id) / str(document_id) / internal_name


def _ensure_private_directory(path: Path) -> None:
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        raise DocumentStorageError(StorageErrorCode.UNAVAILABLE) from None
    # En Windows el modo es parcial; se aplica el mejor esfuerzo sin filtrar la ruta.
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass


def store_document(
    *, organization_id: UUID, document_id: UUID, internal_name: str, data: bytes
) -> None:
    """Escribe bytes bajo la clave derivada; la ruta nunca sale del directorio base."""
    path = _key_path(organization_id, document_id, internal_name)
    _ensure_private_directory(path)
    try:
        path.write_bytes(data)
    except OSError:
        raise DocumentStorageError(StorageErrorCode.UNAVAILABLE) from None
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_document(*, organization_id: UUID, document_id: UUID, internal_name: str) -> bytes:
    path = _key_path(organization_id, document_id, internal_name)
    try:
        return path.read_bytes()
    except OSError:
        raise DocumentStorageError(StorageErrorCode.UNAVAILABLE) from None


def delete_document(*, organization_id: UUID, document_id: UUID, internal_name: str) -> None:
    path = _key_path(organization_id, document_id, internal_name)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        raise DocumentStorageError(StorageErrorCode.UNAVAILABLE) from None
