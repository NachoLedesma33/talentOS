from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as DBSession

from app.assessment import service as assessment_service
from app.assessment.schemas import (
    AssessmentComparisonResult,
    AssessmentListResponse,
    AssessmentResult,
    RequirementEvaluationResult,
    ReviewDecision,
    RunAssessmentRequest,
)
from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User

router = APIRouter(prefix="/api/v1/assessment", tags=["assessment"])

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


def _http_error(exc: assessment_service.AssessmentDomainError) -> HTTPException:
    """Traduce códigos de dominio a HTTP sin filtrar evidencia ni datos del tenant."""
    if exc.code == "not_found":
        return HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Evaluación o postulación no encontrada."
        )
    if exc.code == "forbidden":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.")
    if exc.code == "application_mismatch":
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Las evaluaciones comparadas deben pertenecer a la misma postulación.",
        )
    if exc.code == "review_pending":
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Quedan criterios pendientes de revisión (needs_review o partial). "
                "Revíselos antes de completar la revisión."
            ),
        )
    if exc.code == "assessment_conflict":
        return HTTPException(status.HTTP_409_CONFLICT, detail="Conflicto con el estado actual.")
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


@router.post("/run", response_model=AssessmentResult, status_code=status.HTTP_201_CREATED)
def run_assessment(
    response: Response,
    _origin: OriginChecked,
    payload: RunAssessmentRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> AssessmentResult:
    """Crea la evaluación de la versión vigente o devuelve la existente (200)."""
    try:
        outcome = assessment_service.run_assessment_for_api(
            db,
            organization_id=active_organization.id,
            application_id=payload.application_id,
            actor_id=actor.id,
        )
    except assessment_service.AssessmentDomainError as exc:
        raise _http_error(exc) from None
    response.status_code = status.HTTP_201_CREATED if outcome.created else status.HTTP_200_OK
    return outcome.result


@router.get("/", response_model=AssessmentListResponse)
def list_assessments(
    active_organization: CurrentOrganization,
    db: DbDependency,
    application_id: Annotated[uuid.UUID | None, Query()] = None,
    candidate_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssessmentListResponse:
    try:
        return assessment_service.list_assessments_for_api(
            db,
            organization_id=active_organization.id,
            application_id=application_id,
            candidate_id=candidate_id,
            limit=limit,
            offset=offset,
        )
    except assessment_service.AssessmentDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{assessment_id}", response_model=AssessmentResult)
def get_assessment(
    assessment_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> AssessmentResult:
    try:
        return assessment_service.get_assessment_detail(
            db,
            organization_id=active_organization.id,
            assessment_id=assessment_id,
        )
    except assessment_service.AssessmentDomainError as exc:
        raise _http_error(exc) from None


@router.get("/{assessment_id}/compare", response_model=AssessmentComparisonResult)
def compare_assessments(
    assessment_id: uuid.UUID,
    other_id: Annotated[uuid.UUID, Query()],
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> AssessmentComparisonResult:
    try:
        return assessment_service.compare_assessments(
            db,
            organization_id=active_organization.id,
            base_id=assessment_id,
            other_id=other_id,
        )
    except assessment_service.AssessmentDomainError as exc:
        raise _http_error(exc) from None


@router.patch(
    "/{assessment_id}/evaluations/{evaluation_id}/review",
    response_model=RequirementEvaluationResult,
)
def review_evaluation(
    _origin: OriginChecked,
    assessment_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    payload: ReviewDecision,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    member: WriteMember,
    db: DbDependency,
) -> RequirementEvaluationResult:
    """Aplica la corrección humana con rol explícito y auditoría de metadatos."""
    try:
        return assessment_service.review_evaluation(
            db,
            organization_id=active_organization.id,
            assessment_id=assessment_id,
            evaluation_id=evaluation_id,
            actor_id=actor.id,
            actor_role=member.role,
            decision=payload,
        )
    except assessment_service.AssessmentDomainError as exc:
        raise _http_error(exc) from None


@router.post("/{assessment_id}/review-complete", response_model=AssessmentResult)
def complete_review(
    _origin: OriginChecked,
    assessment_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    member: WriteMember,
    db: DbDependency,
) -> AssessmentResult:
    """Cierra la revisión humana cuando no quedan criterios pendientes."""
    try:
        return assessment_service.complete_review(
            db,
            organization_id=active_organization.id,
            assessment_id=assessment_id,
            actor_id=actor.id,
            actor_role=member.role,
        )
    except assessment_service.AssessmentDomainError as exc:
        raise _http_error(exc) from None
