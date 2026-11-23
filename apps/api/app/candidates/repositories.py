from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.sql.elements import ColumnElement

from app.candidates.models import Candidate, CandidateNote, CandidateProfileStatus


def get_candidate(
    db: DBSession, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> Candidate | None:
    """Devuelve el candidato solo si pertenece a la organización autenticada."""
    stmt = select(Candidate).where(
        Candidate.organization_id == organization_id,
        Candidate.id == candidate_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def _search_filter(q: str | None) -> ColumnElement[bool] | None:
    clean = q.strip().lower() if q is not None else ""
    if not clean:
        return None
    pattern = f"%{clean}%"
    return or_(
        func.lower(Candidate.name).like(pattern),
        func.lower(Candidate.email).like(pattern),
    )


def list_candidates(
    db: DBSession,
    organization_id: uuid.UUID,
    q: str | None = None,
    status: CandidateProfileStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Candidate]:
    """Lista candidatos del tenant con búsqueda portable y paginación."""
    stmt = select(Candidate).where(Candidate.organization_id == organization_id)
    search = _search_filter(q)
    if search is not None:
        stmt = stmt.where(search)
    if status is not None:
        stmt = stmt.where(Candidate.profile_status == status)
    stmt = stmt.order_by(Candidate.created_at, Candidate.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count_candidates(
    db: DBSession,
    organization_id: uuid.UUID,
    q: str | None = None,
    status: CandidateProfileStatus | None = None,
) -> int:
    """Cuenta los candidatos del tenant con los mismos filtros, sin paginar."""
    stmt = select(func.count()).select_from(Candidate).where(
        Candidate.organization_id == organization_id
    )
    search = _search_filter(q)
    if search is not None:
        stmt = stmt.where(search)
    if status is not None:
        stmt = stmt.where(Candidate.profile_status == status)
    return int(db.scalar(stmt) or 0)


def get_note(
    db: DBSession,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    note_id: uuid.UUID,
) -> CandidateNote | None:
    """Devuelve la nota solo si su candidato pertenece a la organización."""
    stmt = (
        select(CandidateNote)
        .join(Candidate, Candidate.id == CandidateNote.candidate_id)
        .where(
            Candidate.organization_id == organization_id,
            CandidateNote.candidate_id == candidate_id,
            CandidateNote.id == note_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_notes(
    db: DBSession, organization_id: uuid.UUID, candidate_id: uuid.UUID
) -> list[CandidateNote]:
    """Lista notas de un candidato propio; nunca las de otra organización."""
    stmt = (
        select(CandidateNote)
        .join(Candidate, Candidate.id == CandidateNote.candidate_id)
        .where(
            Candidate.organization_id == organization_id,
            CandidateNote.candidate_id == candidate_id,
        )
        .order_by(CandidateNote.created_at, CandidateNote.id)
    )
    return list(db.execute(stmt).scalars().all())
