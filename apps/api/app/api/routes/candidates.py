from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.audit.models import AuditLog
from app.candidates import service as candidates_service
from app.candidates.models import Candidate, CandidateNote, CandidateProfileStatus
from app.candidates.schemas import (
    ActivityEntry,
    CandidateCreate,
    CandidateListResponse,
    CandidateResponse,
    CandidateUpdate,
    NoteCreate,
    NoteResponse,
)
from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
WriteMember = Annotated[
    Membership,
    Depends(
        require_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
        )
    ),
]
NoteReader = Annotated[
    Membership,
    Depends(
        require_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
            MembershipRole.REVIEWER,
        )
    ),
]


def _http_error(exc: candidates_service.CandidatesDomainError) -> HTTPException:
    """Traduce errores del dominio sin filtrar existencia entre organizaciones."""
    if isinstance(exc, candidates_service.CandidateNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="Candidato no encontrado.")
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


@router.get("/", response_model=CandidateListResponse)
def list_candidates(
    active_organization: CurrentOrganization,
    db: DbDependency,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[CandidateProfileStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CandidateListResponse:
    candidates, total = candidates_service.list_candidates(
        db,
        organization_id=active_organization.id,
        q=q,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return CandidateListResponse(items=candidates, total=total, limit=limit, offset=offset)


@router.post("/", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    _origin: OriginChecked,
    payload: CandidateCreate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> Candidate:
    try:
        return candidates_service.create_candidate(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            **payload.model_dump(),
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None


@router.get("/export")
def export_candidates(
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: NoteReader,
    db: DbDependency,
) -> dict[str, object]:
    try:
        return candidates_service.export_candidates(
            db, organization_id=active_organization.id, actor_id=actor.id
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> Candidate:
    try:
        return candidates_service.get_candidate(
            db, organization_id=active_organization.id, candidate_id=candidate_id
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None


@router.patch("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(
    _origin: OriginChecked,
    candidate_id: uuid.UUID,
    payload: CandidateUpdate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> Candidate:
    try:
        return candidates_service.update_candidate(
            db,
            organization_id=active_organization.id,
            candidate_id=candidate_id,
            actor_id=actor.id,
            **payload.model_dump(exclude_unset=True),
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{candidate_id}/notes", response_model=list[NoteResponse])
def list_notes(
    candidate_id: uuid.UUID,
    active_organization: CurrentOrganization,
    _member: NoteReader,
    db: DbDependency,
) -> list[CandidateNote]:
    try:
        return candidates_service.list_notes(
            db, organization_id=active_organization.id, candidate_id=candidate_id
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None


@router.post(
    "/{candidate_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED
)
def add_note(
    _origin: OriginChecked,
    candidate_id: uuid.UUID,
    payload: NoteCreate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> CandidateNote:
    try:
        return candidates_service.add_note(
            db,
            organization_id=active_organization.id,
            candidate_id=candidate_id,
            author_id=actor.id,
            body=payload.body,
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{candidate_id}/activity", response_model=list[ActivityEntry])
def get_activity(
    candidate_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> list[AuditLog]:
    try:
        return candidates_service.get_activity(
            db, organization_id=active_organization.id, candidate_id=candidate_id
        )
    except candidates_service.CandidatesDomainError as exc:
        raise _http_error(exc) from None
