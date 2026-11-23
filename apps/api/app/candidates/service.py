from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DBSession

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

MAX_NOTE_BODY_LENGTH = 2000


class CandidatesDomainError(Exception):
    """Error determinista del dominio de candidatos."""


class CandidateValidationError(CandidatesDomainError):
    """Dato de entrada inválido según las reglas del dominio."""


class CandidateNotFoundError(CandidatesDomainError):
    """El candidato no existe en la organización autenticada."""


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
