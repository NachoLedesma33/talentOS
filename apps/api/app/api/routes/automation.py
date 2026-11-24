"""API REST del motor de automatización.

Router delgado: autenticación, autorización, contratos y mapeo de errores.
Las reglas, la idempotencia y las transiciones viven en el servicio de dominio.
Las respuestas solo contienen IDs, enums y metadatos: sin tenant, CV, PII ni
rutas de storage.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.audit.service import record_audit
from app.automation import service as automation_service
from app.automation import tasks as automation_tasks
from app.automation.models import (
    Automation,
    AutomationDomainError,
    AutomationRun,
    AutomationRunEvent,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationRunStatus,
    AutomationStatus,
    AutomationTenantMismatchError,
    InvalidAutomationTransitionError,
)
from app.automation.repositories import (
    get_approval,
    get_automation,
    get_run_by_key,
    get_version,
    list_approvals_for_run,
    list_run_events,
)
from app.automation.schemas import (
    ApprovalDecisionResult,
    ApprovalItem,
    AutomationCreateRequest,
    AutomationDecisionRequest,
    AutomationDetail,
    AutomationEventCount,
    AutomationExecutionRequest,
    AutomationListResponse,
    AutomationSnapshot,
    AutomationStatusUpdate,
    AutomationSummary,
    AutomationTestResult,
    AutomationVersionCreate,
    AutomationVersionResult,
    RunDetail,
    RunEventItem,
    RunEventListResponse,
    RunListResponse,
    RunQueueResult,
    RunSummary,
)
from app.core.logging import log_structured
from app.db.session import get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
ReadMember = Annotated[
    Membership,
    Depends(require_roles(*tuple(MembershipRole))),
]
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

_NOT_FOUND = "Recurso de automatización no encontrado."
_BROKER_CODE = "broker_unavailable"
_RESOURCE_AUTOMATION = "automation"
_RESOURCE_RUN = "automation_run"

# Metadatos verificables; se excluyen notas, correos, rutas y organization_id.
_PUBLIC_EVENT_KEYS = frozenset(
    {
        "action_id",
        "action_index",
        "action_type",
        "approval_id",
        "attempt",
        "condition_count",
        "correlation_id",
        "decision",
        "draft_id",
        "from_stage",
        "kind",
        "matched",
        "reason_code",
        "resource_id",
        "run_id",
        "status",
        "target_stage",
        "template_id",
        "to_stage",
    }
)


def _request_id(request: Request) -> str:
    value: object = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


def _http_error(exc: AutomationDomainError) -> HTTPException:
    """Traduce códigos de dominio a HTTP sin mensajes con datos del tenant."""
    if isinstance(exc, AutomationTenantMismatchError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if isinstance(exc, InvalidAutomationTransitionError):
        return HTTPException(
            status.HTTP_409_CONFLICT, detail="Estado incompatible con la operación."
        )
    code = str(exc)
    if code in {"automation_not_found", "run_not_found", "approval_not_found"}:
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if code == "permission_denied":
        return HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.")
    if code in {"invalid_decision", "invalid_idempotency_key", "invalid_name"}:
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


def _log(
    event: str,
    *,
    request_id: str,
    organization_id: uuid.UUID,
    run_id: uuid.UUID | None,
    correlation_id: uuid.UUID,
    result: str,
    error_code: str | None = None,
) -> None:
    """Registra solo IDs, código estable y resultado; nunca notas ni CV."""
    message = f"{event} run_id={run_id} result={result}"
    if error_code:
        message += f" error_code={error_code}"
    log_structured(
        logging.INFO if error_code is None else logging.WARNING,
        message,
        request_id=request_id,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


def _require_automation(
    db: DBSession, organization_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation:
    automation = get_automation(db, organization_id, automation_id)
    if automation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return automation


def _snapshot(db: DBSession, automation: Automation) -> AutomationSnapshot | None:
    version = get_version(
        db, automation.organization_id, automation.id, automation.current_version
    )
    if version is None:
        return None
    return AutomationSnapshot(
        trigger=validate_safe_payload(dict(version.trigger)),
        conditions=[validate_safe_payload(dict(item)) for item in version.conditions],
        actions=[validate_safe_payload(dict(item)) for item in version.actions],
        created_at=version.created_at,
    )


def _automation_summary(automation: Automation) -> AutomationSummary:
    return AutomationSummary(
        id=automation.id,
        name=automation.name,
        status=automation.status,
        current_version=automation.current_version,
        created_at=automation.created_at,
        updated_at=automation.updated_at,
    )


def _automation_detail(db: DBSession, automation: Automation) -> AutomationDetail:
    return AutomationDetail(
        **_automation_summary(automation).model_dump(),
        active_version=_snapshot(db, automation),
    )


def _run_summary(run: AutomationRun) -> RunSummary:
    return RunSummary(
        id=run.id,
        automation_id=run.automation_id,
        version=run.version,
        mode=run.mode,
        status=run.status,
        correlation_id=run.correlation_id,
        trigger_event_type=run.trigger_event_type,
        error_code=run.error_code,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _run_detail(db: DBSession, run: AutomationRun) -> RunDetail:
    draft_ids: list[uuid.UUID] = []
    for event in list_run_events(db, run.organization_id, run.id, limit=100):
        raw_id: object = event.payload.get("draft_id")
        if isinstance(raw_id, str):
            try:
                draft_ids.append(uuid.UUID(raw_id))
            except ValueError:
                continue
    approvals = list_approvals_for_run(db, run.organization_id, run.id, limit=100)
    return RunDetail(
        **_run_summary(run).model_dump(),
        started_at=run.started_at,
        finished_at=run.finished_at,
        draft_ids=draft_ids,
        approval_ids=[approval.id for approval in approvals],
    )


def _event_summary(db: DBSession, run: AutomationRun) -> list[AutomationEventCount]:
    counts: dict[AutomationRunEventType, int] = {}
    for event in list_run_events(db, run.organization_id, run.id, limit=100):
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return [
        AutomationEventCount(event_type=event_type, count=count)
        for event_type, count in counts.items()
    ]


def _public_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return validate_safe_payload(
        {key: value for key, value in payload.items() if key in _PUBLIC_EVENT_KEYS}
    )


# --- Rutas de ejecución (estáticas primero, antes de /{automation_id}) -----


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    active_organization: CurrentOrganization,
    db: DbDependency,
    status_filter: Annotated[AutomationRunStatus | None, Query(alias="status")] = None,
    mode: Annotated[AutomationRunMode | None, Query(alias="mode")] = None,
    automation_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunListResponse:
    """Lista paginada y tenant-scoped; `mode` se filtra con enum, no con texto."""
    filters = [AutomationRun.organization_id == active_organization.id]
    if status_filter is not None:
        filters.append(AutomationRun.status == status_filter)
    if mode is not None:
        filters.append(AutomationRun.mode == mode)
    if automation_id is not None:
        filters.append(AutomationRun.automation_id == automation_id)
    total = (
        db.scalar(select(func.count()).select_from(AutomationRun).where(*filters)) or 0
    )
    rows = db.scalars(
        select(AutomationRun)
        .where(*filters)
        .order_by(AutomationRun.created_at.desc(), AutomationRun.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return RunListResponse(
        items=[_run_summary(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(
    run_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
) -> RunDetail:
    """Detalle saneado; sin payload de postulación, tenant ni storage."""
    try:
        run = automation_service.get_run_detail(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            run_id=run_id,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    return _run_detail(db, run)


@router.get("/runs/{run_id}/events", response_model=RunEventListResponse)
def list_events(
    run_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunEventListResponse:
    """Timeline paginado con payload reducido a metadatos verificables."""
    try:
        run = automation_service.get_run_detail(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            run_id=run_id,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    total = (
        db.scalar(
            select(func.count())
            .select_from(AutomationRunEvent)
            .where(
                AutomationRunEvent.organization_id == active_organization.id,
                AutomationRunEvent.run_id == run.id,
            )
        )
        or 0
    )
    events = automation_service.list_run_events(
        db,
        organization_id=active_organization.id,
        actor_id=actor.id,
        actor_role=_member.role,
        run_id=run.id,
        limit=limit,
        offset=offset,
    )
    return RunEventListResponse(
        items=[
            RunEventItem(
                event_type=event.event_type,
                created_at=event.created_at,
                correlation_id=run.correlation_id,
                payload=_public_payload(event.payload),
            )
            for event in events
        ],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalItem])
def list_approvals(
    run_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
) -> list[ApprovalItem]:
    """Aprobaciones sin payload sensible; la decisión la registra el dominio."""
    try:
        approvals = automation_service.list_approvals(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            run_id=run_id,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    return [
        ApprovalItem(
            id=approval.id,
            action_type=approval.action_type,
            status=approval.status,
            created_at=approval.created_at,
            decided_at=approval.decided_at,
        )
        for approval in approvals
    ]


@router.post(
    "/runs/{run_id}/approvals/{approval_id}/decide",
    response_model=ApprovalDecisionResult,
)
def decide_approval(
    request: Request,
    _origin: OriginChecked,
    run_id: uuid.UUID,
    approval_id: uuid.UUID,
    payload: AutomationDecisionRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> ApprovalDecisionResult:
    """Actor de sesión, nunca del body; `note` no se persiste ni se audita."""
    approval = get_approval(db, active_organization.id, approval_id)
    if approval is None or approval.run_id != run_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    try:
        decided = automation_service.decide_approval(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            approval_id=approval_id,
            decision=payload.decision,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    run = automation_service.get_run_detail(
        db,
        organization_id=active_organization.id,
        actor_id=actor.id,
        actor_role=_member.role,
        run_id=run_id,
    )
    _log(
        "automation.approval_decided",
        request_id=_request_id(request),
        organization_id=active_organization.id,
        run_id=run.id,
        correlation_id=run.correlation_id,
        result=decided.status.value,
    )
    return ApprovalDecisionResult(
        id=decided.id,
        run_id=decided.run_id,
        action_type=decided.action_type,
        status=decided.status,
        decided_by=decided.decided_by,
        decided_at=decided.decided_at,
        run_status=run.status,
    )


@router.post("/runs/{run_id}/cancel", response_model=RunDetail)
def cancel_run(
    request: Request,
    _origin: OriginChecked,
    run_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> RunDetail:
    """Cancela estados no terminales; el dominio audita la transición."""
    try:
        canceled = automation_service.cancel_run(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            run_id=run_id,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    _log(
        "automation.run_cancelled",
        request_id=_request_id(request),
        organization_id=active_organization.id,
        run_id=canceled.id,
        correlation_id=canceled.correlation_id,
        result=canceled.status.value,
    )
    return _run_detail(db, canceled)


# --- Configuración de automatizaciones ------------------------------------


@router.post("", response_model=AutomationSummary, status_code=status.HTTP_201_CREATED)
def create_automation(
    _origin: OriginChecked,
    payload: AutomationCreateRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AutomationSummary:
    """Crea un borrador; la configuración se envía como versión inmutable."""
    try:
        automation = automation_service.create_automation(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            name=payload.name,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    return _automation_summary(automation)


@router.get("", response_model=AutomationListResponse)
def list_automations(
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: ReadMember,
    db: DbDependency,
    status_filter: Annotated[AutomationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AutomationListResponse:
    """Listado paginado del tenant; sin recursos de otras organizaciones."""
    rows = automation_service.list_automations(
        db,
        organization_id=active_organization.id,
        actor_id=actor.id,
        actor_role=_member.role,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    filters = [Automation.organization_id == active_organization.id]
    if status_filter is not None:
        filters.append(Automation.status == status_filter)
    total = db.scalar(select(func.count()).select_from(Automation).where(*filters)) or 0
    return AutomationListResponse(
        items=[_automation_summary(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{automation_id}", response_model=AutomationDetail)
def get_automation_detail(
    automation_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> AutomationDetail:
    """Detalle con versión activa saneada; sin organization_id ni secretos."""
    automation = _require_automation(db, active_organization.id, automation_id)
    return _automation_detail(db, automation)


@router.patch("/{automation_id}", response_model=AutomationDetail)
def update_automation_status(
    _origin: OriginChecked,
    automation_id: uuid.UUID,
    payload: AutomationStatusUpdate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AutomationDetail:
    """Aplica transiciones válidas; el motor audita activación y desactivación."""
    try:
        if payload.status is AutomationStatus.ACTIVE:
            automation = automation_service.activate_automation(
                db,
                organization_id=active_organization.id,
                actor_id=actor.id,
                actor_role=_member.role,
                automation_id=automation_id,
            )
        elif payload.status is AutomationStatus.INACTIVE:
            automation = automation_service.deactivate_automation(
                db,
                organization_id=active_organization.id,
                actor_id=actor.id,
                actor_role=_member.role,
                automation_id=automation_id,
            )
        elif payload.status is AutomationStatus.ARCHIVED:
            automation = automation_service.archive_automation(
                db,
                organization_id=active_organization.id,
                actor_id=actor.id,
                actor_role=_member.role,
                automation_id=automation_id,
            )
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Estado no soportado."
            )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    return _automation_detail(db, automation)


@router.post(
    "/{automation_id}/versions",
    response_model=AutomationVersionResult,
    status_code=status.HTTP_201_CREATED,
)
def add_version(
    _origin: OriginChecked,
    automation_id: uuid.UUID,
    payload: AutomationVersionCreate,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AutomationVersionResult:
    """Congela una nueva configuración; el snapshot existente nunca se reescribe."""
    try:
        version = automation_service.add_version(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            automation_id=automation_id,
            version=payload,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    return AutomationVersionResult(
        id=version.id,
        automation_id=version.automation_id,
        version=version.version,
        created_at=version.created_at,
    )


@router.post("/{automation_id}/test", response_model=AutomationTestResult)
def test_automation(
    response: Response,
    _origin: OriginChecked,
    automation_id: uuid.UUID,
    payload: AutomationExecutionRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AutomationTestResult:
    """Dry-run sin efectos: 201 la primera vez, 200 si la clave ya existía."""
    existing = get_run_by_key(
        db, active_organization.id, automation_id, payload.idempotency_key
    )
    try:
        run = automation_service.test_automation(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            automation_id=automation_id,
            idempotency_key=payload.idempotency_key,
            application_id=payload.application_id,
            correlation_id=payload.correlation_id,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None
    response.status_code = (
        status.HTTP_201_CREATED if existing is None else status.HTTP_200_OK
    )
    return AutomationTestResult(
        id=run.id,
        automation_id=run.automation_id,
        status=run.status,
        mode=run.mode,
        correlation_id=run.correlation_id,
        event_summary=_event_summary(db, run),
    )


@router.post(
    "/{automation_id}/run",
    response_model=RunQueueResult,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_run(
    request: Request,
    _origin: OriginChecked,
    automation_id: uuid.UUID,
    payload: AutomationExecutionRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> RunQueueResult | JSONResponse:
    """Persiste `pending` y encola; sin broker no hay run ni cambio de estado."""
    existing = get_run_by_key(
        db, active_organization.id, automation_id, payload.idempotency_key
    )
    if existing is not None:
        # Misma clave = misma ejecución: no se reencola ni se reaudita.
        return RunQueueResult(
            id=existing.id,
            status=existing.status,
            queued=False,
            correlation_id=existing.correlation_id,
        )
    try:
        run = automation_service.create_run(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            automation_id=automation_id,
            idempotency_key=payload.idempotency_key,
            application_id=payload.application_id,
            correlation_id=payload.correlation_id,
        )
    except AutomationDomainError as exc:
        raise _http_error(exc) from None

    request_id = _request_id(request)
    try:
        automation_tasks.execute_run.delay(
            str(active_organization.id),
            str(actor.id),
            _member.role.value,
            str(run.id),
            str(run.correlation_id),
        )
    except Exception:
        # Nunca propagar mensaje, URL ni traza del broker al cliente ni a logs.
        db.rollback()
        _log(
            "automation.run_broker_failed",
            request_id=request_id,
            organization_id=active_organization.id,
            run_id=run.id,
            correlation_id=run.correlation_id,
            result="failed",
            error_code=_BROKER_CODE,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": _BROKER_CODE,
                    "message": "Cola no disponible; la ejecución no se creó.",
                    "request_id": request_id,
                }
            },
        )

    record_audit(
        db,
        organization_id=active_organization.id,
        actor_id=actor.id,
        action="automation.run_started",
        resource_type=_RESOURCE_RUN,
        resource_id=run.id,
    )
    db.commit()
    _log(
        "automation.run_queued",
        request_id=request_id,
        organization_id=active_organization.id,
        run_id=run.id,
        correlation_id=run.correlation_id,
        result="queued",
    )
    return RunQueueResult(
        id=run.id,
        status=run.status,
        queued=True,
        correlation_id=run.correlation_id,
    )


__all__ = ["router"]
