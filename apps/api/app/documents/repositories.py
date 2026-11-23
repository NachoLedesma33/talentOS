from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.documents.models import Document, DocumentExtraction, ExtractedField


def get_document(
    db: DBSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    """Devuelve el documento solo si pertenece a la organización autenticada."""
    stmt = select(Document).where(
        Document.organization_id == organization_id,
        Document.id == document_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_documents(
    db: DBSession,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """Lista documentos del tenant con filtro opcional de candidato y paginación."""
    stmt = select(Document).where(Document.organization_id == organization_id)
    if candidate_id is not None:
        stmt = stmt.where(Document.candidate_id == candidate_id)
    stmt = stmt.order_by(Document.created_at, Document.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_documents(
    db: DBSession, organization_id: uuid.UUID, candidate_id: uuid.UUID | None = None
) -> int:
    """Cuenta los documentos del tenant con los mismos filtros, sin paginar."""
    stmt = select(func.count()).select_from(Document).where(
        Document.organization_id == organization_id
    )
    if candidate_id is not None:
        stmt = stmt.where(Document.candidate_id == candidate_id)
    return int(db.scalar(stmt) or 0)


def get_extraction(
    db: DBSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
) -> DocumentExtraction | None:
    """Lee una extracción solo si su documento pertenece a la organización."""
    stmt = (
        select(DocumentExtraction)
        .join(Document, Document.id == DocumentExtraction.document_id)
        .where(
            Document.organization_id == organization_id,
            DocumentExtraction.document_id == document_id,
            DocumentExtraction.id == extraction_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_fields(
    db: DBSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
) -> list[ExtractedField]:
    """Lista campos de una extracción propia; nunca los de otro tenant o documento."""
    stmt = (
        select(ExtractedField)
        .join(DocumentExtraction, DocumentExtraction.id == ExtractedField.extraction_id)
        .join(Document, Document.id == DocumentExtraction.document_id)
        .where(
            Document.organization_id == organization_id,
            DocumentExtraction.document_id == document_id,
            ExtractedField.extraction_id == extraction_id,
        )
        .order_by(ExtractedField.created_at, ExtractedField.id)
    )
    return list(db.execute(stmt).scalars().all())
