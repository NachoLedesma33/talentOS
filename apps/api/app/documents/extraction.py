from __future__ import annotations

import io
import uuid
from enum import StrEnum

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.documents import storage
from app.documents.storage import DocumentStorageError
from app.documents.validation import MAX_PAGES

# Claves internas y estables de la extracción determinista: aún no hay LLM ni prompt.
EXTRACTION_PROVIDER = "local_text"
EXTRACTION_MODEL = "pypdf+python-docx"
EXTRACTION_PROMPT_VERSION = "text-v1"


class ExtractionErrorCode(StrEnum):
    EMPTY = "empty_document"
    CORRUPT = "corrupt_document"
    TOO_MANY_PAGES = "too_many_pages"
    STORAGE_UNAVAILABLE = "storage_unavailable"


class ExtractionError(Exception):
    """Fallo de extracción: código estable, sin fragmentos del documento."""

    def __init__(self, code: ExtractionErrorCode | str) -> None:
        self.code = code.value if isinstance(code, ExtractionErrorCode) else code
        super().__init__(self.code)


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def _pdf_pages(data: bytes) -> list[tuple[int, str]]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PAGES:
            raise ExtractionError(ExtractionErrorCode.TOO_MANY_PAGES)
        return [
            (page_number, page.extract_text() or "")
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    except ExtractionError:
        raise
    except Exception:
        # pypdf puede fallar de muchas formas: una sola categoría pública, sin causa ni texto.
        raise ExtractionError(ExtractionErrorCode.CORRUPT) from None


def _docx_pages(data: bytes) -> list[tuple[int, str]]:
    try:
        document = DocxDocument(io.BytesIO(data))
        paragraphs = [
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]
    except Exception:
        raise ExtractionError(ExtractionErrorCode.CORRUPT) from None
    # DOCX no conserva paginación: una única página lógica con sus párrafos.
    return [(1, "\n".join(paragraphs))]


def _pages_to_result(pages: list[tuple[int, str]]) -> list[dict[str, object]]:
    if not pages or all(not text.strip() for _, text in pages):
        raise ExtractionError(ExtractionErrorCode.EMPTY)

    result: list[dict[str, object]] = []
    offset = 0
    for page_number, text in pages:
        result.append(
            {
                "page": page_number,
                "text": text,
                "start_offset": offset,
                "end_offset": offset + len(text),
            }
        )
        offset += len(text)
    return result


def extract_text(
    *,
    document_id: uuid.UUID | str,
    internal_name: str,
    extension: str,
    data: bytes | None = None,
    organization_id: uuid.UUID | str | None = None,
) -> list[dict[str, object]]:
    """Extrae página y texto; `data` evita releer si el worker ya leyó el storage."""
    try:
        if data is None:
            if organization_id is None:
                raise ExtractionError(ExtractionErrorCode.CORRUPT)
            data = storage.read_document(
                organization_id=_as_uuid(organization_id),
                document_id=_as_uuid(document_id),
                internal_name=internal_name,
            )
    except ExtractionError:
        raise
    except (DocumentStorageError, ValueError, OSError):
        raise ExtractionError(ExtractionErrorCode.STORAGE_UNAVAILABLE) from None

    if not data:
        raise ExtractionError(ExtractionErrorCode.EMPTY)

    normalized_extension = extension.lower()
    if normalized_extension == ".pdf":
        pages = _pdf_pages(data)
    elif normalized_extension == ".docx":
        pages = _docx_pages(data)
    else:
        raise ExtractionError(ExtractionErrorCode.CORRUPT)
    return _pages_to_result(pages)
