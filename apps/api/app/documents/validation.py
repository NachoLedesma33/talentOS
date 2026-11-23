from __future__ import annotations

import io
import zipfile
from enum import StrEnum
from pathlib import PurePosixPath

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx"})
ALLOWED_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_SIZE_BYTES = 10 * 1024 * 1024
MAX_PAGES = 50

_DOCX_MEMBER = "word/document.xml"


class UploadErrorCode(StrEnum):
    INVALID_EXTENSION = "invalid_extension"
    INVALID_MIME = "invalid_mime"
    INVALID_SIGNATURE = "invalid_signature"
    EMPTY_FILE = "empty_file"
    TOO_LARGE = "too_large"


class UploadValidationError(ValueError):
    """Error estable de upload: código sin payload, nombre ni ruta del archivo."""

    def __init__(self, code: UploadErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


def extract_extension(filename: str) -> str:
    # Las barras de clientes Windows y POSIX se tratan igual; nunca se usa la ruta.
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


def _docx_is_valid(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return _DOCX_MEMBER in archive.namelist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, EOFError):
        return False


def validate_upload(*, filename: str, content_type: str, data: bytes) -> None:
    """Valida extensión, MIME declarado, firma real y tamaño antes de tocar storage."""
    extension = extract_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(UploadErrorCode.INVALID_EXTENSION)

    declared = content_type.split(";", 1)[0].strip().lower()
    if declared != ALLOWED_MIME[extension]:
        raise UploadValidationError(UploadErrorCode.INVALID_MIME)

    if not data:
        raise UploadValidationError(UploadErrorCode.EMPTY_FILE)
    if len(data) > MAX_SIZE_BYTES:
        raise UploadValidationError(UploadErrorCode.TOO_LARGE)

    valid_signature = (
        data.startswith(b"%PDF-")
        if extension == ".pdf"
        else _docx_is_valid(data)
    )
    if not valid_signature:
        raise UploadValidationError(UploadErrorCode.INVALID_SIGNATURE)
