from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.applications.models import Application
from app.audit.models import AuditLog
from app.audit.service import list_resource_events, record_audit
from app.candidates.models import (
    Candidate,
    CandidateNote,
    CandidateProfileStatus,
)
from app.candidates.repositories import (
    count_candidates as count_candidate_rows,
)
from app.candidates.repositories import (
    get_candidate as get_candidate_row,
)
from app.candidates.repositories import (
    list_candidates as list_candidate_rows,
)
from app.candidates.repositories import (
    list_notes as list_note_rows,
)
from app.documents.models import Document

MAX_NOTE_BODY_LENGTH = 2000
MAX_EXPORT_CANDIDATES = 1000


class CandidatesDomainError(Exception):
    """Error determinista del dominio de candidatos."""


class CandidateValidationError(CandidatesDomainError):
    """Dato de entrada inválido según las reglas del dominio."""


class CandidateNotFoundError(CandidatesDomainError):
    """El candidato no existe en la organización autenticada."""


class CandidateExportTooLargeError(CandidatesDomainError):
    """La organización supera el tope de candidatos exportables en una solicitud."""


def _require_candidate(
    db: DBSession, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> Candidate:
    candidate = get_candidate_row(db, organization_id, candidate_id)
    if candidate is None:
        raise CandidateNotFoundError
    return candidate


def _normalize_email(value: str) -> str:
    clean = value.strip().lower()
    if not clean:
        raise CandidateValidationError("email must not be blank")
    return clean


def get_candidate(
    db: DBSession, *, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> Candidate:
    """Expone el candidato propio al router; el repositorio aplica el filtro de tenant."""
    return _require_candidate(db, organization_id, candidate_id)


def list_candidates(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    q: str | None = None,
    status: CandidateProfileStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Candidate], int]:
    """Devuelve la página de candidatos del tenant y el total sin paginar."""
    candidates = list_candidate_rows(
        db, organization_id, q=q, status=status, limit=limit, offset=offset
    )
    total = count_candidate_rows(db, organization_id, q=q, status=status)
    return candidates, total


def create_candidate(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    email: str,
    location: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Candidate:
    """Crea un candidato en borrador; el email se normaliza a minúsculas."""
    clean_name = name.strip()
    if not clean_name:
        raise CandidateValidationError("name must not be blank")

    candidate = Candidate(
        organization_id=organization_id,
        name=clean_name,
        email=_normalize_email(email),
        location=location.strip() if location is not None else None,
        profile_status=CandidateProfileStatus.DRAFT,
    )
    db.add(candidate)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="candidate.created",
        resource_type="candidate",
        resource_id=candidate.id,
    )
    db.commit()
    return candidate


def update_candidate(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    name: str | None = None,
    email: str | None = None,
    location: str | None = None,
    profile_status: CandidateProfileStatus | None = None,
    actor_id: uuid.UUID | None = None,
) -> Candidate:
    """Actualiza campos explícitos; `None` significa «sin cambio»."""
    candidate = _require_candidate(db, organization_id, candidate_id)
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise CandidateValidationError("name must not be blank")
        candidate.name = clean_name
    if email is not None:
        candidate.email = _normalize_email(email)
    if location is not None:
        candidate.location = location.strip()
    if profile_status is not None:
        candidate.profile_status = profile_status

    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="candidate.updated",
        resource_type="candidate",
        resource_id=candidate.id,
    )
    db.commit()
    return candidate


def add_note(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    author_id: uuid.UUID,
    body: str,
) -> CandidateNote:
    """Registra una nota interna no vacía, ligada al candidato y a su autor."""
    candidate = _require_candidate(db, organization_id, candidate_id)
    clean_body = body.strip()
    if not clean_body:
        raise CandidateValidationError("note body must not be blank")
    if len(clean_body) > MAX_NOTE_BODY_LENGTH:
        raise CandidateValidationError("note body is too long")

    note = CandidateNote(candidate_id=candidate.id, author_id=author_id, body=clean_body)
    db.add(note)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=author_id,
        action="note.added",
        resource_type="candidate",
        resource_id=candidate.id,
    )
    db.commit()
    return note


def list_notes(
    db: DBSession, *, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> list[CandidateNote]:
    """Lista notas de un candidato verificado en la organización activa."""
    _require_candidate(db, organization_id, candidate_id)
    return list_note_rows(db, organization_id, candidate_id)


def get_activity(
    db: DBSession, *, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> list[AuditLog]:
    """Historial de auditoría del candidato, sin payloads ni datos personales."""
    _require_candidate(db, organization_id, candidate_id)
    return list_resource_events(
        db, organization_id, "candidate", candidate_id
    )


def _export_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def export_candidates(
    db: DBSession, *, organization_id: uuid.UUID, actor_id: uuid.UUID
) -> dict[str, object]:
    """Exporta datos propios del tenant; audita el acceso sin registrar payload."""
    total = count_candidate_rows(db, organization_id)
    if total > MAX_EXPORT_CANDIDATES:
        raise CandidateExportTooLargeError

    candidates = list_candidate_rows(
        db, organization_id, limit=MAX_EXPORT_CANDIDATES, offset=0
    )
    candidate_ids = {candidate.id for candidate in candidates}
    notes = list(
        db.scalars(
            select(CandidateNote)
            .join(Candidate, CandidateNote.candidate_id == Candidate.id)
            .where(Candidate.organization_id == organization_id)
            .order_by(CandidateNote.created_at, CandidateNote.id)
        ).all()
    )
    applications = list(
        db.scalars(
            select(Application)
            .where(Application.organization_id == organization_id)
            .order_by(Application.created_at, Application.id)
        ).all()
    )
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.organization_id == organization_id)
            .order_by(Document.created_at, Document.id)
        ).all()
    )

    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="candidate.exported",
        resource_type="organization",
        resource_id=organization_id,
    )
    db.commit()

    return {
        "schema_version": 1,
        "organization_id": str(organization_id),
        "candidates": [
            {
                "id": str(candidate.id),
                "name": candidate.name,
                "email": candidate.email,
                "location": candidate.location,
                "profile_status": _export_value(candidate.profile_status),
                "created_at": _export_value(candidate.created_at),
                "updated_at": _export_value(candidate.updated_at),
            }
            for candidate in candidates
        ],
        "notes": [
            {
                "id": str(note.id),
                "candidate_id": str(note.candidate_id),
                "author_id": str(note.author_id),
                "body": note.body,
                "created_at": _export_value(note.created_at),
                "updated_at": _export_value(note.updated_at),
            }
            for note in notes
            if note.candidate_id in candidate_ids
        ],
        "applications": [
            {
                "id": str(application.id),
                "candidate_id": str(application.candidate_id),
                "job_id": str(application.job_id),
                "stage": _export_value(application.stage),
                "source": _export_value(application.source),
                "created_at": _export_value(application.created_at),
                "updated_at": _export_value(application.updated_at),
            }
            for application in applications
            if application.candidate_id in candidate_ids
        ],
        "documents": [
            {
                "id": str(document.id),
                "candidate_id": str(document.candidate_id),
                "original_filename": document.original_filename,
                "content_type": document.content_type,
                "size_bytes": document.size_bytes,
                "checksum_sha256": document.checksum_sha256,
                "status": _export_value(document.status),
                "created_at": _export_value(document.created_at),
            }
            for document in documents
            if document.candidate_id in candidate_ids
        ],
    }
