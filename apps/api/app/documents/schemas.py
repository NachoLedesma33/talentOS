from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.documents.models import (
    DocumentStatus,
    ExtractedFieldName,
    ExtractedFieldStatus,
    ExtractionStatus,
)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(_ResponseModel):
    """Metadatos públicos: sin ruta de storage, nombre interno ni organization_id."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    original_filename: str
    content_type: str
    extension: str
    size_bytes: int
    checksum_sha256: str
    status: DocumentStatus
    page_count: int | None
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DownloadUrlResponse(BaseModel):
    url: str
    expires_at: datetime


class EvidenceResponse(_ResponseModel):
    """Cita verificable: documento, página y fragmento; nunca página completa."""

    document_id: uuid.UUID
    page: int
    quote: str
    offset: int | None = None


class FieldResponse(_ResponseModel):
    """Campo extraído listo para revisión; la confirmación siempre la decide la API."""

    id: uuid.UUID
    field_name: ExtractedFieldName
    value: object | None
    status: ExtractedFieldStatus
    evidence: list[EvidenceResponse]
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None


class ExtractionResponse(_ResponseModel):
    """Extracción revisable: expone evidencia acotada, nunca `pages` ni `internal_name`."""

    id: uuid.UUID
    document_id: uuid.UUID
    provider: str
    model: str
    prompt_version: str
    status: ExtractionStatus
    injection_detected: bool
    review_required: bool
    fields: list[FieldResponse]
    created_at: datetime
    updated_at: datetime


class ReviewRequest(BaseModel):
    """Corrección opcional; `value=None` significa confirmar el valor extraído."""

    model_config = ConfigDict(extra="forbid")

    value: dict[str, object] | None = Field(default=None, max_length=32)


class ReviewResponse(_ResponseModel):
    """Estado devuelto por la API tras una confirmación individual."""

    field_id: uuid.UUID
    field_name: ExtractedFieldName
    status: ExtractedFieldStatus
    value: object | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None


class ReviewSummaryResponse(BaseModel):
    """Resumen de la confirmación en bloque; los dudosos siguen en revisión."""

    document_id: uuid.UUID
    extraction_id: uuid.UUID
    confirmed: int
    corrected: int
    needs_review: int
    pending: int
    total: int
    review_required: bool
    injection_detected: bool
