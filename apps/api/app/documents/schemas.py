from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.documents.models import DocumentStatus


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
