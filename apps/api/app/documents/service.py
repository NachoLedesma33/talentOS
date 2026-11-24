from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.audit.service import record_audit
from app.candidates.repositories import get_candidate as get_candidate_row
from app.core.logging import log_structured
from app.documents import storage
from app.documents.extraction import (
    EXTRACTION_MODEL,
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_PROVIDER,
)
from app.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
    ExtractedField,
    ExtractedFieldStatus,
    ExtractionStatus,
)
from app.documents.repositories import count_documents as count_document_rows
from app.documents.repositories import get_document as get_document_row
from app.documents.repositories import get_extraction_for_worker
from app.documents.repositories import get_field as get_field_row
from app.documents.repositories import get_latest_extraction as get_latest_extraction_row
from app.documents.repositories import list_documents as list_document_rows
from app.documents.repositories import list_fields as list_field_rows
from app.documents.schemas import (
    DownloadUrlResponse,
    EvidenceResponse,
    ExtractionResponse,
    FieldResponse,
    ReviewResponse,
    ReviewSummaryResponse,
)
from app.documents.storage import DocumentStorageError, StorageErrorCode
from app.documents.storage import _key_path as storage_key_path
from app.documents.tasks import extract_document as extract_document_task
from app.documents.tokens import create_download_token
from app.documents.validation import ALLOWED_MIME, extract_extension, validate_upload
from app.identity.models import MembershipRole
from app.identity.repositories import get_membership, user_belongs_to_organization

_RESOURCE_TYPE = "document"
_DOWNLOAD_PATH = "/api/v1/documents/files"
_DOWNLOAD_TTL_SECONDS = 60
_EXTRACTION_WRITE_ROLES = frozenset(
    {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.RECRUITER}
)
_BROKER_FAILURE_CODE = "broker_unavailable"


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


def issue_download_url(document: Document) -> DownloadUrlResponse:
    """Firma un enlace interno de 60 s sin filtrar ruta de storage en la respuesta."""
    token, expires_at = create_download_token(
        document_id=document.id,
        organization_id=document.organization_id,
        ttl_seconds=_DOWNLOAD_TTL_SECONDS,
    )
    return DownloadUrlResponse(url=f"{_DOWNLOAD_PATH}/{token}", expires_at=expires_at)


def resolve_download_path(document: Document) -> Path:
    """Resuelve la ruta privada desde la fila del tenant, sin exponerla al cliente."""
    try:
        path = storage_key_path(document.organization_id, document.id, document.internal_name)
        if not path.is_file():
            raise DocumentNotFoundError
        return path
    except (DocumentStorageError, OSError):
        raise DocumentNotFoundError from None


def prepare_download(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> tuple[Document, Path]:
    """Autoriza el token, comprueba el archivo y audita solo metadatos del acceso."""
    document = _require_document(db, organization_id, document_id)
    path = resolve_download_path(document)
    try:
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="document.downloaded",
            resource_type=_RESOURCE_TYPE,
            resource_id=document.id,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return document, path


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


def _mark_broker_failure(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    """Segunda transacción: deja rastro del fallo del broker sin guardar la excepción."""
    db.rollback()
    document = db.get(Document, document_id)
    extraction = db.get(DocumentExtraction, extraction_id)
    if document is not None and document.organization_id == organization_id:
        document.status = DocumentStatus.FAILED
        document.error_code = _BROKER_FAILURE_CODE
    if extraction is not None and extraction.document_id == document_id:
        extraction.status = ExtractionStatus.FAILED
        extraction.pages = []
        extraction.error_code = _BROKER_FAILURE_CODE
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="document.extraction_failed",
        resource_type=_RESOURCE_TYPE,
        resource_id=document_id,
    )
    db.commit()


def start_extraction(
    db: DBSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    uploader_id: uuid.UUID,
) -> dict[str, object]:
    """Autoriza, crea la extracción pendiente y encola IDs; sin importar el archivo."""
    membership = get_membership(db, uploader_id, organization_id)
    if membership is None or membership.role not in _EXTRACTION_WRITE_ROLES:
        raise DocumentsDomainError("forbidden")

    document = _require_document(db, organization_id, document_id)
    if document.status not in (DocumentStatus.UPLOADED, DocumentStatus.FAILED):
        raise DocumentsDomainError("invalid_status")

    extraction = get_extraction_for_worker(
        db, document.id, EXTRACTION_PROVIDER, EXTRACTION_PROMPT_VERSION
    )
    if extraction is not None and extraction.status is ExtractionStatus.COMPLETED:
        raise DocumentsDomainError("invalid_status")
    if extraction is None:
        extraction = DocumentExtraction(
            id=uuid.uuid4(),
            document_id=document.id,
            provider=EXTRACTION_PROVIDER,
            model=EXTRACTION_MODEL,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            status=ExtractionStatus.PENDING,
            pages=[],
        )
        db.add(extraction)
    else:
        extraction.status = ExtractionStatus.PENDING
        extraction.pages = []
        extraction.error_code = None

    document.status = DocumentStatus.PROCESSING
    document.page_count = None
    document.error_code = None
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=uploader_id,
        action="document.extraction_requested",
        resource_type=_RESOURCE_TYPE,
        resource_id=document.id,
    )
    db.commit()

    document_id_value = document.id
    extraction_id = extraction.id
    correlation_id = str(uuid.uuid4())
    try:
        extract_document_task.delay(str(document_id_value), str(organization_id))
    except Exception:
        # Nunca registrar mensaje, URL ni traza del broker: solo el código estable.
        _mark_broker_failure(
            db,
            organization_id=organization_id,
            document_id=document_id_value,
            extraction_id=extraction_id,
            actor_id=uploader_id,
        )
        log_structured(
            logging.WARNING,
            f"document_extraction_broker_failed document_id={document_id_value} result=failed",
            correlation_id=correlation_id,
            organization_id=str(organization_id),
        )
        final_status = DocumentStatus.FAILED
    else:
        log_structured(
            logging.INFO,
            f"document_extraction_requested document_id={document_id_value} result=queued",
            correlation_id=correlation_id,
            organization_id=str(organization_id),
        )
        final_status = DocumentStatus.PROCESSING

    return {
        "document_id": str(document_id_value),
        "extraction_id": str(extraction_id),
        "status": final_status.value,
        "provider": EXTRACTION_PROVIDER,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
    }


_FIELD_RESOURCE_TYPE = "extracted_field"
_TERMINAL_STATUSES = frozenset(
    {ExtractedFieldStatus.CONFIRMED, ExtractedFieldStatus.CORRECTED}
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _require_review_writer(
    db: DBSession, organization_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """Autoriza la confirmación en el dominio, no solo en la capa HTTP."""
    membership = get_membership(db, actor_id, organization_id)
    if membership is None or membership.role not in _EXTRACTION_WRITE_ROLES:
        raise DocumentsDomainError("forbidden")


def _resolve_extraction(
    db: DBSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[Document, DocumentExtraction]:
    document = _require_document(db, organization_id, document_id)
    extraction = get_latest_extraction_row(db, organization_id, document_id)
    if extraction is None:
        raise DocumentNotFoundError
    return document, extraction


def _evidence_response(raw: object) -> EvidenceResponse | None:
    if not isinstance(raw, Mapping):
        return None
    item = cast(Mapping[str, object], raw)
    raw_document_id = item.get("document_id")
    page = item.get("page")
    quote = item.get("quote")
    offset = item.get("offset")
    if not isinstance(raw_document_id, str) or not isinstance(page, int):
        return None
    if not isinstance(quote, str):
        return None
    try:
        document_id = uuid.UUID(raw_document_id)
    except ValueError:
        return None
    return EvidenceResponse(
        document_id=document_id,
        page=page,
        quote=quote,
        offset=offset if isinstance(offset, int) else None,
    )


def _field_response(field: ExtractedField) -> FieldResponse:
    raw_evidence = cast(object, field.evidence)
    evidence: list[EvidenceResponse] = []
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            parsed = _evidence_response(item)
            if parsed is not None:
                evidence.append(parsed)
    return FieldResponse(
        id=field.id,
        field_name=field.field_name,
        value=field.value,
        status=field.status,
        evidence=evidence,
        confirmed_by=field.confirmed_by,
        confirmed_at=field.confirmed_at,
    )


def _extraction_response(
    extraction: DocumentExtraction, fields: list[ExtractedField]
) -> ExtractionResponse:
    return ExtractionResponse(
        id=extraction.id,
        document_id=extraction.document_id,
        provider=extraction.provider,
        model=extraction.model,
        prompt_version=extraction.prompt_version,
        status=extraction.status,
        injection_detected=extraction.injection_detected,
        review_required=extraction.review_required,
        fields=[_field_response(field) for field in fields],
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


def review_response(field: ExtractedField) -> ReviewResponse:
    return ReviewResponse(
        field_id=field.id,
        field_name=field.field_name,
        status=field.status,
        value=field.value,
        confirmed_by=field.confirmed_by,
        confirmed_at=field.confirmed_at,
    )


def _all_resolved(fields: list[ExtractedField]) -> bool:
    return bool(fields) and all(field.status in _TERMINAL_STATUSES for field in fields)


def _refresh_review_flag(extraction: DocumentExtraction, fields: list[ExtractedField]) -> None:
    # Una señal de inyección nunca se limpia automáticamente: obliga a revisión humana.
    extraction.review_required = extraction.injection_detected or not _all_resolved(fields)


def _record_field_confirmation(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    field_id: uuid.UUID,
) -> None:
    """Auditoría sin valores: solo actor, tenant, acción y resource ID."""
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="document.field_confirmed",
        resource_type=_FIELD_RESOURCE_TYPE,
        resource_id=field_id,
    )


def _record_review_completion(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="document.review_completed",
        resource_type=_RESOURCE_TYPE,
        resource_id=document_id,
    )


def _original_value(value: object) -> object:
    """Compara correcciones `{text: ...}`/`{items: ...}` con el valor extraído."""
    if isinstance(value, Mapping):
        item = cast(Mapping[str, object], value)
        if len(item) == 1 and "text" in item:
            return item["text"]
        if len(item) == 1 and "items" in item:
            return item["items"]
    return value


def list_extraction_fields(
    db: DBSession, *, organization_id: uuid.UUID, document_id: uuid.UUID
) -> ExtractionResponse:
    """Devuelve campos y señales de revisión del documento propio, sin texto crudo."""
    _, extraction = _resolve_extraction(db, organization_id, document_id)
    fields = list_field_rows(db, organization_id, document_id, extraction.id)
    return _extraction_response(extraction, fields)


def confirm_field(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    field_id: uuid.UUID,
    actor_id: uuid.UUID,
    value: dict[str, object] | None = None,
) -> ExtractedField:
    """Confirma o corrige un campo explícitamente; la corrección cambia su estado."""
    _require_review_writer(db, organization_id, actor_id)
    document, extraction = _resolve_extraction(db, organization_id, document_id)
    field = get_field_row(db, organization_id, document_id, extraction.id, field_id)
    if field is None:
        raise DocumentNotFoundError
    if field.status in _TERMINAL_STATUSES:
        raise DocumentsDomainError("invalid_status")

    original = field.value
    if value is not None:
        field.value = value
        field.status = (
            ExtractedFieldStatus.CORRECTED
            if _original_value(value) != original
            else ExtractedFieldStatus.CONFIRMED
        )
    else:
        field.status = ExtractedFieldStatus.CONFIRMED
    field.confirmed_by = actor_id
    field.confirmed_at = _utcnow()

    fields = list_field_rows(db, organization_id, document_id, extraction.id)
    was_complete = _all_resolved(fields)
    _refresh_review_flag(extraction, fields)
    _record_field_confirmation(
        db, organization_id=organization_id, actor_id=actor_id, field_id=field.id
    )
    if not was_complete and _all_resolved(fields):
        _record_review_completion(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            document_id=document.id,
        )
    db.commit()
    return field


def confirm_all(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> ReviewSummaryResponse:
    """Confirma solo campos con evidencia; los dudosos quedan en `needs_review`."""
    _require_review_writer(db, organization_id, actor_id)
    document, extraction = _resolve_extraction(db, organization_id, document_id)
    fields = list_field_rows(db, organization_id, document_id, extraction.id)
    if not fields:
        raise DocumentsDomainError("invalid_status")

    unresolved = [field for field in fields if field.status not in _TERMINAL_STATUSES]
    if extraction.injection_detected and unresolved:
        # La inyección exige revisión individual antes de cualquier confirmación en bloque.
        raise DocumentsDomainError("review_required")

    was_complete = _all_resolved(fields)
    now = _utcnow()
    for field in fields:
        if field.status is ExtractedFieldStatus.EXTRACTED and field.evidence:
            field.status = ExtractedFieldStatus.CONFIRMED
            field.confirmed_by = actor_id
            field.confirmed_at = now
            _record_field_confirmation(
                db, organization_id=organization_id, actor_id=actor_id, field_id=field.id
            )
        elif field.status in (
            ExtractedFieldStatus.NEEDS_REVIEW,
            ExtractedFieldStatus.MISSING,
        ):
            # Nunca auto-confirmar evidencia ausente o dudosa.
            field.status = ExtractedFieldStatus.NEEDS_REVIEW
            field.confirmed_by = None
            field.confirmed_at = None

    _refresh_review_flag(extraction, fields)
    if not was_complete and _all_resolved(fields):
        _record_review_completion(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            document_id=document.id,
        )
    db.commit()

    return ReviewSummaryResponse(
        document_id=document.id,
        extraction_id=extraction.id,
        confirmed=sum(1 for field in fields if field.status is ExtractedFieldStatus.CONFIRMED),
        corrected=sum(1 for field in fields if field.status is ExtractedFieldStatus.CORRECTED),
        needs_review=sum(
            1 for field in fields if field.status is ExtractedFieldStatus.NEEDS_REVIEW
        ),
        pending=sum(
            1
            for field in fields
            if field.status in (ExtractedFieldStatus.EXTRACTED, ExtractedFieldStatus.MISSING)
        ),
        total=len(fields),
        review_required=extraction.review_required,
        injection_detected=extraction.injection_detected,
    )

