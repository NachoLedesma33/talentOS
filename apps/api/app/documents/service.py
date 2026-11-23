from __future__ import annotations

import hashlib
import secrets
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.audit.service import record_audit
from app.candidates.repositories import get_candidate as get_candidate_row
from app.documents import storage
from app.documents.models import Document, DocumentStatus
from app.documents.repositories import count_documents as count_document_rows
from app.documents.repositories import get_document as get_document_row
from app.documents.repositories import list_documents as list_document_rows
from app.documents.storage import DocumentStorageError, StorageErrorCode
from app.documents.validation import ALLOWED_MIME, extract_extension, validate_upload
from app.identity.repositories import user_belongs_to_organization

_RESOURCE_TYPE = "document"


class DocumentsDomainError(Exception):
    """Error determinista del dominio de documentos; mensaje es solo el código."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DocumentNotFoundError(DocumentsDomainError):
    """El documento, candidato o usuario no existe en la organización autenticada."""

    def __init__(self) -> None:
        super().__init__("not_found")


def _require_document(
    db: DBSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = get_document_row(db, organization_id, document_id)
    if document is None:
        raise DocumentNotFoundError
    return document


def create_document(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    uploader_id: uuid.UUID,
    filename: str,
    content_type: str,
    data: bytes,
) -> Document:
    """Valida, guarda bytes privados y registra metadatos; sin IA ni worker."""
    validate_upload(filename=filename, content_type=content_type, data=data)

    if get_candidate_row(db, organization_id, candidate_id) is None:
        raise DocumentNotFoundError
    if not user_belongs_to_organization(db, uploader_id, organization_id):
        raise DocumentNotFoundError

    extension = extract_extension(filename)
    document_id = uuid.uuid4()
    internal_name = f"{secrets.token_urlsafe(32)}{extension}"
    checksum = hashlib.sha256(data).hexdigest()
    original_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]

    try:
        storage.store_document(
            organization_id=organization_id,
            document_id=document_id,
            internal_name=internal_name,
            data=data,
        )
    except DocumentStorageError:
        raise
    except OSError:
        raise DocumentStorageError(StorageErrorCode.UNAVAILABLE) from None

    document = Document(
        id=document_id,
        organization_id=organization_id,
        candidate_id=candidate_id,
        uploaded_by=uploader_id,
        original_filename=original_filename,
        internal_name=internal_name,
        content_type=ALLOWED_MIME[extension],
        extension=extension,
        size_bytes=len(data),
        checksum_sha256=checksum,
        status=DocumentStatus.UPLOADED,
    )
    try:
        db.add(document)
        db.flush()
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=uploader_id,
            action="document.uploaded",
            resource_type=_RESOURCE_TYPE,
            resource_id=document.id,
        )
        db.commit()
    except SQLAlchemyError:
        # Sin fila huérfana ni bytes huérfanos si falla la persistencia.
        db.rollback()
        try:
            storage.delete_document(
                organization_id=organization_id,
                document_id=document.id,
                internal_name=internal_name,
            )
        except DocumentStorageError:
            pass
        raise
    return document


def get_document(
    db: DBSession, *, organization_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    """Expone el documento propio al router; el repositorio filtra por tenant."""
    return _require_document(db, organization_id, document_id)


def list_documents(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    """Devuelve la página de documentos del tenant y el total sin paginar."""
    documents = list_document_rows(
        db, organization_id, candidate_id=candidate_id, limit=limit, offset=offset
    )
    total = count_document_rows(db, organization_id, candidate_id=candidate_id)
    return documents, total


def delete_document(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Borra bytes y fila propios; deja la fila intacta si falla el storage."""
    document = _require_document(db, organization_id, document_id)
    internal_name = document.internal_name

    storage.delete_document(
        organization_id=organization_id,
        document_id=document_id,
        internal_name=internal_name,
    )

    try:
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="document.deleted",
            resource_type=_RESOURCE_TYPE,
            resource_id=document.id,
        )
        db.delete(document)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
