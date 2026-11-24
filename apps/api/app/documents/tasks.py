from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.logging import log_structured
from app.db.session import SessionLocal
from app.documents import storage
from app.documents.analysis import analyze_extraction
from app.documents.extraction import (
    EXTRACTION_MODEL,
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_PROVIDER,
    ExtractionError,
    extract_text,
)
from app.documents.models import Document, DocumentExtraction, DocumentStatus, ExtractionStatus
from app.documents.repositories import get_document_for_worker, get_extraction_for_worker
from app.documents.storage import DocumentStorageError, StorageErrorCode
from app.workers.celery_app import celery_app


def _correlation_id() -> str:
    """Una ejecución = un correlation_id; en worker se reusa el id de la tarea."""
    current: object = celery_app.current_task
    request_id = getattr(getattr(current, "request", None), "id", None)
    return str(request_id) if request_id else str(uuid.uuid4())


def _log_event(
    level: int,
    event: str,
    *,
    document_id: uuid.UUID | str,
    organization_id: uuid.UUID | str,
    correlation_id: str,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log de una línea: solo IDs, código estable y resultado; nunca texto del CV."""
    message = f"{event} document_id={document_id} result={result}"
    if error_code:
        message += f" error_code={error_code}"
    log_structured(
        level,
        message,
        correlation_id=correlation_id,
        organization_id=str(organization_id),
    )


def _record_failure(
    db: DBSession,
    *,
    document: Document,
    extraction: DocumentExtraction | None,
    code: str,
) -> None:
    if extraction is None:
        extraction = DocumentExtraction(
            id=uuid.uuid4(),
            document_id=document.id,
            provider=EXTRACTION_PROVIDER,
            model=EXTRACTION_MODEL,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            status=ExtractionStatus.FAILED,
            pages=[],
            error_code=code,
        )
        db.add(extraction)
    extraction.status = ExtractionStatus.FAILED
    extraction.pages = []
    extraction.error_code = code
    document.status = DocumentStatus.FAILED
    document.error_code = code
    db.commit()


@celery_app.task(  # type: ignore[untyped-decorator]  # El decorador de Celery no es tipable sin stubs.
    name="documents.extract", acks_late=True, reject_on_worker_lost=True
)
def extract_document(document_id: str, organization_id: str) -> None:
    """Extrae texto del documento propio y persiste el resultado; sin prompt ni LLM."""
    correlation_id = _correlation_id()
    db: DBSession = SessionLocal()
    try:
        try:
            document_uuid = uuid.UUID(document_id)
            tenant_uuid = uuid.UUID(organization_id)
        except (TypeError, ValueError):
            _log_event(
                logging.WARNING,
                "document_extraction_failed",
                document_id=document_id,
                organization_id=organization_id,
                correlation_id=correlation_id,
                result="aborted",
                error_code="invalid_context",
            )
            return

        document = get_document_for_worker(db, document_uuid)
        if document is None:
            _log_event(
                logging.WARNING,
                "document_extraction_failed",
                document_id=document_uuid,
                organization_id=tenant_uuid,
                correlation_id=correlation_id,
                result="aborted",
                error_code="not_found",
            )
            return

        # El tenant viaja explícitamente y se comprueba antes de leer cualquier byte.
        if document.organization_id != tenant_uuid:
            _log_event(
                logging.WARNING,
                "document_extraction_failed",
                document_id=document_uuid,
                organization_id=tenant_uuid,
                correlation_id=correlation_id,
                result="aborted",
                error_code="organization_mismatch",
            )
            return

        extraction = get_extraction_for_worker(
            db, document.id, EXTRACTION_PROVIDER, EXTRACTION_PROMPT_VERSION
        )
        if (
            extraction is not None
            and extraction.status is ExtractionStatus.COMPLETED
            and document.status is DocumentStatus.PROCESSED
        ):
            _log_event(
                logging.INFO,
                "document_extraction_duplicate",
                document_id=document.id,
                organization_id=tenant_uuid,
                correlation_id=correlation_id,
                result="skipped",
            )
            return

        try:
            data = storage.read_document(
                organization_id=document.organization_id,
                document_id=document.id,
                internal_name=document.internal_name,
            )
            pages = extract_text(
                document_id=document.id,
                internal_name=document.internal_name,
                extension=document.extension,
                data=data,
            )
        except ExtractionError as exc:
            _record_failure(db, document=document, extraction=extraction, code=exc.code)
            _log_event(
                logging.WARNING,
                "document_extraction_failed",
                document_id=document.id,
                organization_id=tenant_uuid,
                correlation_id=correlation_id,
                result="failed",
                error_code=exc.code,
            )
            return
        except (DocumentStorageError, OSError, ValueError):
            code = StorageErrorCode.UNAVAILABLE.value
            _record_failure(db, document=document, extraction=extraction, code=code)
            _log_event(
                logging.WARNING,
                "document_extraction_failed",
                document_id=document.id,
                organization_id=tenant_uuid,
                correlation_id=correlation_id,
                result="failed",
                error_code=code,
            )
            return

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
        extraction.status = ExtractionStatus.COMPLETED
        extraction.pages = pages
        extraction.error_code = None
        document.status = DocumentStatus.PROCESSED
        document.page_count = len(pages)
        document.error_code = None
        db.commit()
        _log_event(
            logging.INFO,
            "document_extraction_completed",
            document_id=document.id,
            organization_id=tenant_uuid,
            correlation_id=correlation_id,
            result="completed",
        )
        # Solo el mock determinista está habilitado en esta unidad; el remoto queda
        # configurado pero sin ejecución automática hasta su evaluación (Fase 6).
        if get_settings().LLM_PROVIDER == "mock":
            analyze_extraction(db, tenant_uuid, document.id, extraction)
    except SQLAlchemyError:
        db.rollback()
        _log_event(
            logging.ERROR,
            "document_extraction_failed",
            document_id=document_id,
            organization_id=organization_id,
            correlation_id=correlation_id,
            result="failed",
            error_code="database_unavailable",
        )
    except Exception:
        # Ninguna excepción de librería sube al worker: evitar trazas con contenido del CV.
        db.rollback()
        _log_event(
            logging.ERROR,
            "document_extraction_failed",
            document_id=document_id,
            organization_id=organization_id,
            correlation_id=correlation_id,
            result="failed",
            error_code="internal_error",
        )
    finally:
        db.close()
