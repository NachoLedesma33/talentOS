from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DBSession

from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.interviews import service as interviews_service
from app.interviews.models import InterviewDomainError, InterviewGuideStatus
from app.interviews.schemas import (
    GenerateGuideRequest,
    GuideGenerationResponse,
    GuideRevisionListResponse,
    InterviewFeedbackListResponse,
    InterviewFeedbackResult,
    InterviewFeedbackSubmitRequest,
    InterviewGuideDetail,
    InterviewGuideListResponse,
    InterviewGuideUpdate,
    InterviewQuestionCreateRequest,
    InterviewQuestionResult,
    InterviewQuestionUpdateRequest,
)
from app.interviews.service import InterviewPolicyError

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])

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

_NOT_FOUND = "Guía, pregunta o postulación no encontrada."
_PUBLISH_BLOCKED = (
    "No se puede publicar: quedan preguntas rechazadas o con revisión pendiente. "
    "Corríjalas, apruébelas y vuelva a intentarlo."
)


def _request_id(request: Request) -> str:
    value: object = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


def _correlation_id(request: Request) -> str:
    value: object = getattr(request.state, "correlation_id", None)
    return str(value) if value else _request_id(request)


def _http_error(exc: InterviewDomainError) -> HTTPException:
    """Traduce códigos de dominio a HTTP; nunca devuelve PII ni trazas."""
    code = getattr(exc, "code", str(exc))
    if code == "not_found":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if code == "forbidden":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.")
    if code in {"publish_blocked", "position_conflict", "guide_conflict"} or str(
        code
    ).startswith("Transición"):
        if code == "publish_blocked":
            return HTTPException(status.HTTP_409_CONFLICT, detail=_PUBLISH_BLOCKED)
        return HTTPException(
            status.HTTP_409_CONFLICT, detail="El recurso cambió; recárguelo y reintente."
        )
    if str(code).startswith("provider_") or code == "provider_unavailable":
        return HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Proveedor no disponible; la guía no se generó.",
        )
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


def _policy_error(request: Request, exc: InterviewPolicyError) -> JSONResponse:
    """422 accionable con reason_code, sin texto de la pregunta ni del candidato."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "policy_rejected",
                "message": (
                    "La pregunta no cumple la política de selección. Reformule el texto "
                    "y vuelva a intentarlo."
                ),
                "reason_code": exc.reason_code,
                "request_id": _request_id(request),
            }
        },
    )


@router.post("/guides/generate", response_model=GuideGenerationResponse)
def generate_guide(
    response: Response,
    _origin: OriginChecked,
    payload: GenerateGuideRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> GuideGenerationResponse:
    """Genera o reutiliza la guía; idempotencia y reglas las resuelve el dominio."""
    try:
        result = interviews_service.generate_guide(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            application_id=payload.application_id,
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None
    response.status_code = (
        status.HTTP_201_CREATED if result["created"] else status.HTTP_200_OK
    )
    return GuideGenerationResponse.model_validate(result)


@router.get("/guides", response_model=InterviewGuideListResponse)
def list_guides(
    active_organization: CurrentOrganization,
    db: DbDependency,
    application_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[InterviewGuideStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InterviewGuideListResponse:
    """Lista paginada de guías del tenant con filtros opcionales."""
    return interviews_service.list_guides_for_api(
        db,
        active_organization.id,
        application_id=application_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/guides/{guide_id}", response_model=InterviewGuideDetail)
def get_guide(
    guide_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> InterviewGuideDetail:
    """Detalle saneado con preguntas; sin CV, tenant ni rutas de storage."""
    try:
        return interviews_service.get_guide_detail_for_api(
            db, active_organization.id, guide_id
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.get("/guides/{guide_id}/revisions", response_model=GuideRevisionListResponse)
def list_guide_revisions(
    guide_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GuideRevisionListResponse:
    """Historial por versión con autor y snapshot saneado; paginado."""
    try:
        return interviews_service.list_revisions_for_api(
            db, active_organization.id, guide_id, limit=limit, offset=offset
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.patch("/guides/{guide_id}", response_model=InterviewGuideDetail)
def update_guide(
    request: Request,
    _origin: OriginChecked,
    guide_id: uuid.UUID,
    payload: InterviewGuideUpdate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> InterviewGuideDetail:
    """Edita título/estado; la publicación pendiente se bloquea en el dominio."""
    try:
        return interviews_service.update_guide_for_api(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            guide_id=guide_id,
            payload=payload,
            correlation_id=_correlation_id(request),
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.post(
    "/guides/{guide_id}/questions",
    response_model=InterviewQuestionResult,
    status_code=status.HTTP_201_CREATED,
)
def add_question(
    request: Request,
    _origin: OriginChecked,
    guide_id: uuid.UUID,
    payload: InterviewQuestionCreateRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> InterviewQuestionResult | JSONResponse:
    """Alta manual con revalidación de políticas y auditoría sin PII."""
    try:
        return interviews_service.add_question_for_api(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            guide_id=guide_id,
            payload=payload,
            correlation_id=_correlation_id(request),
        )
    except InterviewPolicyError as exc:
        return _policy_error(request, exc)
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.patch("/questions/{question_id}", response_model=InterviewQuestionResult)
def update_question(
    request: Request,
    _origin: OriginChecked,
    question_id: uuid.UUID,
    payload: InterviewQuestionUpdateRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> InterviewQuestionResult | JSONResponse:
    """Edita texto, foco, competencia, posición o estado permitido por enum."""
    try:
        return interviews_service.update_question_for_api(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            question_id=question_id,
            payload=payload,
            correlation_id=_correlation_id(request),
        )
    except InterviewPolicyError as exc:
        return _policy_error(request, exc)
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.delete("/questions/{question_id}", response_model=InterviewQuestionResult)
def archive_question(
    request: Request,
    _origin: OriginChecked,
    question_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> InterviewQuestionResult:
    """Soft delete: estado `archived`, sin borrado físico."""
    try:
        return interviews_service.archive_question_for_api(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            question_id=question_id,
            correlation_id=_correlation_id(request),
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.post(
    "/questions/{question_id}/feedback",
    response_model=InterviewFeedbackResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    request: Request,
    _origin: OriginChecked,
    question_id: uuid.UUID,
    payload: InterviewFeedbackSubmitRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> InterviewFeedbackResult:
    """Feedback humano sin score ni decisión; entrevistador derivado de sesión."""
    try:
        return interviews_service.submit_feedback_for_api(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            question_id=question_id,
            payload=payload,
            correlation_id=_correlation_id(request),
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None


@router.get("/questions/{question_id}/feedback", response_model=InterviewFeedbackListResponse)
def list_feedback(
    question_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InterviewFeedbackListResponse:
    """Historial de feedback del tenant vinculado a la pregunta y su requisito."""
    try:
        return interviews_service.list_feedback_for_api(
            db,
            active_organization.id,
            question_id,
            limit=limit,
            offset=offset,
        )
    except InterviewDomainError as exc:
        raise _http_error(exc) from None
