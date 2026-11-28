from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.agents import service as agents_service
from app.agents.assistant import (
    AssistantDependencies,
    build_assistant_response,
    build_workspace_assistant_graph,
    initial_assistant_state,
)
from app.agents.checkpoints import SQLAgentCheckpointSaver
from app.agents.contracts import (
    MATCHING_REVIEW_WORKFLOW,
    RECRUITMENT_ORCHESTRATION_WORKFLOW,
    WORKSPACE_ASSISTANT_WORKFLOW,
    AssistantActionAck,
    AssistantMessageRequest,
    AssistantMessageResponse,
)
from app.agents.models import (
    AgentDomainError,
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentTenantMismatchError,
    Approval,
    ApprovalStatus,
)
from app.agents.repositories import (
    decide_approval as persist_approval_decision,
)
from app.agents.repositories import (
    get_agent_run,
    get_agent_run_by_idempotency_key,
    get_approval,
    get_or_create_agent_run,
    list_agent_events,
    list_approvals_for_run,
    update_agent_run_status,
)
from app.agents.schemas import (
    DecideApprovalRequest,
    StartAgentRunRequest,
    StartOrchestrationRunRequest,
    validate_safe_payload,
)
from app.agents.tasks import resume_agent_workflow
from app.agents.tools import build_assistant_registry
from app.agents.workflow import build_config
from app.applications.models import Application
from app.audit.service import record_audit
from app.core.config import get_settings
from app.core.logging import log_structured
from app.db.session import SessionLocal, get_db
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    require_roles,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.llm.registry import get_llm_provider

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

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
AssistantMember = Annotated[
    Membership,
    Depends(
        require_roles(
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
            MembershipRole.VIEWER,
        )
    ),
]

_NOT_FOUND = "Ejecución o aprobación no encontrada."
_BROKER_CODE = "broker_unavailable"
_RESOURCE_TYPE = "agent_run"

# Los eventos de dominio pueden incluir IDs internos; la API solo publica metadatos.
_PUBLIC_EVENT_KEYS = frozenset(
    {
        "action_type",
        "agent_run_id",
        "attempts",
        "approval_id",
        "correlation_id",
        "decided_by",
        "decision",
        "draft_id",
        "duration_ms",
        "error_type",
        "node",
        "resumed",
        "status",
        "statuses_summary",
        "template",
        "char_count",
        "tool",
        "version",
        "workflow",
    }
)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class AgentRunSummary(_ResponseModel):
    """Detalle mínimo de una ejecución; sin tenant, CV ni rutas de storage."""

    id: uuid.UUID
    workflow: str
    version: str
    status: AgentRunStatus
    correlation_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    output_ref: str | None
    job_id: uuid.UUID | None
    candidate_id: uuid.UUID | None


class EventSummary(_ResponseModel):
    event_type: AgentEventType
    count: int


class AgentRunDetail(AgentRunSummary):
    event_summary: list[EventSummary] = Field(default_factory=list)
    event_count: int = 0
    duration_ms: int
    configured_provider: str
    configured_model: str | None


class AgentRunListResponse(_ResponseModel):
    items: list[AgentRunSummary]
    total: int
    limit: int
    offset: int


class AgentEventItem(_ResponseModel):
    event_type: AgentEventType
    created_at: datetime
    correlation_id: uuid.UUID
    payload: dict[str, object]


class AgentEventListResponse(_ResponseModel):
    items: list[AgentEventItem]
    total: int
    limit: int
    offset: int


class ApprovalItem(_ResponseModel):
    id: uuid.UUID
    action_type: str
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None


class ResumeResponse(_ResponseModel):
    agent_run_id: uuid.UUID
    status: AgentRunStatus
    queued: bool
    correlation_id: uuid.UUID


def _http_error(exc: AgentDomainError) -> HTTPException:
    """Traduce códigos de dominio a HTTP sin devolver mensajes con datos del tenant."""
    if isinstance(exc, AgentTenantMismatchError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    code = str(exc)
    if code in {"forbidden", "permission_denied"}:
        return HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente.")
    if code in {
        "invalid_decision",
        "invalid_idempotency_key",
        "invalid_context",
        "unknown_workflow",
        "idempotency_workflow_conflict",
    }:
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")
    if code in {"workflow_not_waiting_approval", "approval_pending", "approval_actor_mismatch"}:
        return HTTPException(
            status.HTTP_409_CONFLICT, detail="Estado de la ejecución incompatible."
        )
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")


def _require_run(
    db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> AgentRun:
    run = get_agent_run(db, organization_id, agent_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return run


def _summary(db: DBSession, run: AgentRun) -> AgentRunSummary:
    job_id, candidate_id = _application_ids(db, run)
    return AgentRunSummary(
        id=run.id,
        workflow=run.workflow,
        version=run.version,
        status=run.status,
        correlation_id=run.correlation_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        output_ref=run.output_ref,
        job_id=job_id,
        candidate_id=candidate_id,
    )


def _event_summary(
    db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> tuple[list[EventSummary], int]:
    total = (
        db.scalar(
            select(func.count())
            .select_from(AgentEvent)
            .where(AgentEvent.agent_run_id == agent_run_id)
        )
        or 0
    )
    counts: dict[AgentEventType, int] = {}
    for event in list_agent_events(db, organization_id, agent_run_id, limit=100):
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return [EventSummary(event_type=key, count=value) for key, value in counts.items()], total


def _duration_ms(run: AgentRun) -> int:
    return max(0, int((run.updated_at - run.created_at).total_seconds() * 1000))


def _application_ids(
    db: DBSession, run: AgentRun
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if not run.input_ref:
        return None, None
    try:
        application_id = uuid.UUID(run.input_ref)
    except ValueError:
        return None, None
    row = db.execute(
        select(Application.job_id, Application.candidate_id).where(
            Application.id == application_id,
            Application.organization_id == run.organization_id,
        )
    ).one_or_none()
    if row is None:
        return None, None
    job_id, candidate_id = row
    return job_id, candidate_id


def _detail(db: DBSession, run: AgentRun) -> AgentRunDetail:
    summary, total = _event_summary(db, run.organization_id, run.id)
    settings = get_settings()
    return AgentRunDetail(
        **_summary(db, run).model_dump(),
        event_summary=summary,
        event_count=total,
        duration_ms=_duration_ms(run),
        configured_provider=settings.LLM_PROVIDER,
        configured_model=settings.LLM_MODEL.strip() or None,
    )


def _public_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Reduce el payload a metadatos verificables; nunca organization_id ni texto libre."""
    return validate_safe_payload(
        {key: value for key, value in payload.items() if key in _PUBLIC_EVENT_KEYS}
    )


def _request_id(request: Request) -> str:
    value: object = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


def _log(
    event: str,
    *,
    request_id: str,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    correlation_id: uuid.UUID,
    result: str,
    error_code: str | None = None,
) -> None:
    """Registra solo IDs, acción y resultado; nunca notas, CV ni secretos."""
    level = logging.INFO if error_code is None else logging.WARNING
    message = f"{event} agent_run_id={agent_run_id} result={result}"
    if error_code:
        message += f" error_code={error_code}"
    log_structured(
        level,
        message,
        request_id=request_id,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


def _assistant_checkpointer() -> BaseCheckpointSaver[str]:
    """Checkpointer aislado por tenant; tests lo fijan sobre SQLite en memoria."""
    return SQLAgentCheckpointSaver(SessionLocal)


def _assistant_config(run: AgentRun) -> RunnableConfig:
    return build_config(organization_id=run.organization_id, agent_run_id=run.id)


def _assistant_dependencies(
    db: DBSession,
    run: AgentRun,
    member: Membership,
    *,
    message: str = "",
    recent_messages: tuple[str, ...] = (),
) -> AssistantDependencies:
    """Une la sesión autenticada con el grafo; el mensaje no se persiste."""
    return AssistantDependencies(
        db=db,
        organization_id=run.organization_id,
        actor_id=run.actor_id,
        actor_role=member.role,
        correlation_id=run.correlation_id,
        agent_run_id=run.id,
        idempotency_key=run.idempotency_key,
        registry=build_assistant_registry(),
        provider=get_llm_provider(),
        checkpointer=_assistant_checkpointer(),
        prompt_context={
            "message": message,
            "recent_messages": list(recent_messages),
        },
    )


def _assistant_initial_state(
    payload: AssistantMessageRequest, run: AgentRun
) -> dict[str, object]:
    return dict(
        initial_assistant_state(
            organization_id=run.organization_id,
            actor_id=run.actor_id,
            correlation_id=run.correlation_id,
            agent_run_id=run.id,
            idempotency_key=run.idempotency_key,
            message=payload.message,
            recent_messages=tuple(item.content for item in payload.recent_messages),
            surface=payload.surface,
            resource_ref=payload.resource_ref,
        )
    )


def _read_assistant_state(graph: Any, config: RunnableConfig) -> dict[str, object]:
    snapshot = graph.get_state(config)
    return dict(snapshot.values or {})


def _assistant_status(state: Mapping[str, object]) -> AgentRunStatus:
    raw = state.get("status")
    try:
        return AgentRunStatus(str(raw)) if raw else AgentRunStatus.PENDING
    except ValueError:
        return AgentRunStatus.FAILED


def _ensure_assistant_approval(
    db: DBSession, run: AgentRun, state: Mapping[str, object]
) -> Approval:
    approval_id = uuid.UUID(str(state.get("approval_id") or ""))
    existing = get_approval(db, run.organization_id, approval_id)
    if existing is not None:
        return existing
    approval = Approval(
        id=approval_id,
        organization_id=run.organization_id,
        agent_run_id=run.id,
        action_type=WORKSPACE_ASSISTANT_WORKFLOW.approval_action_type,
        payload=validate_safe_payload(
            {
                "workflow": WORKSPACE_ASSISTANT_WORKFLOW.workflow,
                "version": WORKSPACE_ASSISTANT_WORKFLOW.version,
                "action_type": WORKSPACE_ASSISTANT_WORKFLOW.approval_action_type,
                "approval_id": str(approval_id),
                "run_id": str(run.id),
            }
        ),
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.flush()
    return approval


def _sync_assistant_run(
    db: DBSession, run: AgentRun, state: Mapping[str, object]
) -> AgentRunStatus:
    status = _assistant_status(state)
    if status not in {AgentRunStatus.PENDING, AgentRunStatus.RUNNING}:
        update_agent_run_status(db, run, status)
    return status


def _start_run_response(
    request: Request,
    response: Response,
    payload: StartAgentRunRequest | StartOrchestrationRunRequest,
    actor: User,
    active_organization: Organization,
    member: Membership,
    db: DBSession,
    *,
    workflow: str,
) -> AgentRunDetail:
    """Arranca cualquier contrato con la misma auditoría, logs y detalle público."""
    existing = get_agent_run_by_idempotency_key(
        db, active_organization.id, payload.idempotency_key
    )
    try:
        view = agents_service.start_workflow(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=member.role,
            application_id=payload.application_id,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id,
            workflow=workflow,
        )
    except AgentDomainError as exc:
        raise _http_error(exc) from None

    run = _require_run(db, active_organization.id, uuid.UUID(str(view["agent_run_id"])))
    created = existing is None
    if created:
        record_audit(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            action="agent.run_started",
            resource_type=_RESOURCE_TYPE,
            resource_id=run.id,
        )
        db.commit()
        _log(
            "agent.run_started",
            request_id=_request_id(request),
            organization_id=active_organization.id,
            agent_run_id=run.id,
            correlation_id=run.correlation_id,
            result="created",
        )
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return _detail(db, run)


@router.post("/assistant/messages", response_model=AssistantMessageResponse)
def post_assistant_message(
    request: Request,
    response: Response,
    _origin: OriginChecked,
    payload: AssistantMessageRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    member: AssistantMember,
    db: DbDependency,
) -> AssistantMessageResponse:
    """Ejecuta el asistente; sin effects hasta aprobación, sin mensaje persistido."""
    existing = get_agent_run_by_idempotency_key(
        db, active_organization.id, payload.idempotency_key
    )
    if existing is not None and existing.workflow != WORKSPACE_ASSISTANT_WORKFLOW.workflow:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitud inválida.")
    run = existing or get_or_create_agent_run(
        db,
        organization_id=active_organization.id,
        workflow=WORKSPACE_ASSISTANT_WORKFLOW.workflow,
        version=WORKSPACE_ASSISTANT_WORKFLOW.version,
        idempotency_key=payload.idempotency_key,
        correlation_id=uuid.uuid4(),
        actor_id=actor.id,
    )
    deps = _assistant_dependencies(
        db,
        run,
        member,
        message=payload.message,
        recent_messages=tuple(item.content for item in payload.recent_messages),
    )
    graph = build_workspace_assistant_graph(deps)
    config = _assistant_config(run)
    created = existing is None
    if created:
        update_agent_run_status(db, run, AgentRunStatus.RUNNING)
        # El checkpointer abre su propia sesión: el run debe ser visible antes de invocar.
        db.commit()
        try:
            graph.invoke(_assistant_initial_state(payload, run), config)
        except GraphInterrupt:
            pass
        state = _read_assistant_state(graph, config)
        run_status = _sync_assistant_run(db, run, state)
        if run_status is AgentRunStatus.WAITING_APPROVAL:
            _ensure_assistant_approval(db, run, state)
        record_audit(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            action="assistant.message_requested",
            resource_type=_RESOURCE_TYPE,
            resource_id=run.id,
        )
        db.commit()
        _log(
            "assistant.message",
            request_id=_request_id(request),
            organization_id=active_organization.id,
            agent_run_id=run.id,
            correlation_id=run.correlation_id,
            result=run_status.value,
        )
    else:
        state = _read_assistant_state(graph, config)
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return build_assistant_response(state, run_id=run.id)


@router.post("/assistant/actions/{action_id}/ack", response_model=AssistantMessageResponse)
def ack_assistant_action(
    request: Request,
    _origin: OriginChecked,
    action_id: uuid.UUID,
    payload: AssistantActionAck,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    member: WriteMember,
    db: DbDependency,
) -> AssistantMessageResponse:
    """Confirma o descarta una acción propuesta; sin effects hasta la decisión."""
    run = get_agent_run_by_idempotency_key(
        db, active_organization.id, payload.idempotency_key
    )
    if run is None or run.workflow != WORKSPACE_ASSISTANT_WORKFLOW.workflow:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    deps = _assistant_dependencies(db, run, member)
    graph = build_workspace_assistant_graph(deps)
    config = _assistant_config(run)
    state = _read_assistant_state(graph, config)
    actions = cast(list[Mapping[str, object]], state.get("proposed_actions") or [])
    if not any(str(item.get("action_id")) == str(action_id) for item in actions):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    approval_id = uuid.UUID(str(state.get("approval_id") or ""))
    approval = get_approval(db, active_organization.id, approval_id)
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    target = (
        ApprovalStatus.APPROVED
        if payload.decision == "applied"
        else ApprovalStatus.REJECTED
    )
    if _assistant_status(state) is not AgentRunStatus.WAITING_APPROVAL:
        if approval.status is target and approval.decided_by == actor.id:
            return build_assistant_response(state, run_id=run.id)
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Estado de la ejecución incompatible."
        )
    try:
        persist_approval_decision(
            db,
            approval,
            decision=target,
            decided_by=actor.id,
            decided_at=datetime.now(UTC),
        )
    except (AgentDomainError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Estado de la ejecución incompatible."
        ) from exc
    resumed = graph.invoke(
        Command(
            resume={
                "decision": target.value,
                "approval_id": str(approval_id),
                "decided_by": str(actor.id),
            }
        ),
        config,
    )
    final_state = (
        dict(resumed)
        if isinstance(resumed, Mapping)
        else _read_assistant_state(graph, config)
    )
    _sync_assistant_run(db, run, final_state)
    record_audit(
        db,
        organization_id=active_organization.id,
        actor_id=actor.id,
        action="assistant.action_ack",
        resource_type="approval",
        resource_id=approval.id,
    )
    db.commit()
    _log(
        "assistant.action_ack",
        request_id=_request_id(request),
        organization_id=active_organization.id,
        agent_run_id=run.id,
        correlation_id=run.correlation_id,
        result=payload.decision,
    )
    return build_assistant_response(final_state, run_id=run.id)


@router.post("/runs", response_model=AgentRunDetail)
def start_run(
    request: Request,
    response: Response,
    _origin: OriginChecked,
    payload: StartAgentRunRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AgentRunDetail:
    """Crea la ejecución o devuelve la existente; la idempotencia la resuelve el dominio."""
    return _start_run_response(
        request,
        response,
        payload,
        actor,
        active_organization,
        _member,
        db,
        workflow=MATCHING_REVIEW_WORKFLOW.workflow,
    )


@router.post("/orchestration/runs", response_model=AgentRunDetail)
def start_orchestration_run(
    request: Request,
    response: Response,
    _origin: OriginChecked,
    payload: StartOrchestrationRunRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AgentRunDetail:
    """Arranca el orquestador dedicado; el workflow no viaja en el body."""
    return _start_run_response(
        request,
        response,
        payload,
        actor,
        active_organization,
        _member,
        db,
        workflow=RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow,
    )


@router.get("/runs", response_model=AgentRunListResponse)
def list_runs(
    active_organization: CurrentOrganization,
    db: DbDependency,
    status_filter: Annotated[AgentRunStatus | None, Query(alias="status")] = None,
    workflow: Annotated[str | None, Query(max_length=100)] = None,
    agent: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[datetime | None, Query(alias="date_from")] = None,
    date_to: Annotated[datetime | None, Query(alias="date_to")] = None,
    job_id: Annotated[uuid.UUID | None, Query()] = None,
    candidate_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentRunListResponse:
    if date_from and date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=UTC)
    if date_to and date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=UTC)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Rango de fechas inválido.")

    filters = [AgentRun.organization_id == active_organization.id]
    if status_filter is not None:
        filters.append(AgentRun.status == status_filter)
    if workflow:
        filters.append(AgentRun.workflow == workflow)
    if agent:
        filters.append(AgentRun.workflow == agent)
    if date_from:
        filters.append(AgentRun.created_at >= date_from)
    if date_to:
        filters.append(AgentRun.created_at <= date_to)
    if job_id or candidate_id:
        application_filters = [Application.organization_id == active_organization.id]
        if job_id:
            application_filters.append(Application.job_id == job_id)
        if candidate_id:
            application_filters.append(Application.candidate_id == candidate_id)
        matching_ids = db.scalars(select(Application.id).where(*application_filters)).all()
        filters.append(AgentRun.input_ref.in_([str(item) for item in matching_ids]))
    total = (
        db.scalar(select(func.count()).select_from(AgentRun).where(*filters)) or 0
    )
    rows = db.scalars(
        select(AgentRun)
        .where(*filters)
        .order_by(AgentRun.created_at.desc(), AgentRun.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return AgentRunListResponse(
        items=[_summary(db, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
def get_run(
    run_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> AgentRunDetail:
    run = _require_run(db, active_organization.id, run_id)
    return _detail(db, run)


@router.get("/runs/{run_id}/events", response_model=AgentEventListResponse)
def list_events(
    run_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentEventListResponse:
    run = _require_run(db, active_organization.id, run_id)
    total = (
        db.scalar(
            select(func.count())
            .select_from(AgentEvent)
            .where(AgentEvent.agent_run_id == run.id)
        )
        or 0
    )
    events = list_agent_events(db, active_organization.id, run.id, limit=limit, offset=offset)
    return AgentEventListResponse(
        items=[
            AgentEventItem(
                event_type=event.event_type,
                created_at=event.created_at,
                correlation_id=event.correlation_id,
                payload=_public_payload(event.payload),
            )
            for event in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalItem])
def list_run_approvals(
    run_id: uuid.UUID,
    active_organization: CurrentOrganization,
    db: DbDependency,
) -> list[ApprovalItem]:
    run = _require_run(db, active_organization.id, run_id)
    return [
        ApprovalItem(
            id=approval.id,
            action_type=approval.action_type,
            status=approval.status,
            created_at=approval.created_at,
            decided_at=approval.decided_at,
        )
        for approval in list_approvals_for_run(db, active_organization.id, run.id)
    ]


@router.post(
    "/runs/{run_id}/approvals/{approval_id}/decide", response_model=AgentRunDetail
)
def decide_run_approval(
    request: Request,
    _origin: OriginChecked,
    run_id: uuid.UUID,
    approval_id: uuid.UUID,
    payload: DecideApprovalRequest,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AgentRunDetail:
    """Decide con actor de sesión; la nota no se persiste ni se registra en logs."""
    try:
        agents_service.decide_approval(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            agent_run_id=run_id,
            approval_id=approval_id,
            decision=payload.decision,
        )
    except AgentDomainError as exc:
        raise _http_error(exc) from None

    run = _require_run(db, active_organization.id, run_id)
    approval = agents_service.get_approval_for_decision(
        db, active_organization.id, approval_id, run_id
    )
    record_audit(
        db,
        organization_id=active_organization.id,
        actor_id=actor.id,
        action="agent.approval_decided",
        resource_type="approval",
        resource_id=approval.id,
    )
    db.commit()
    _log(
        "agent.approval_decided",
        request_id=_request_id(request),
        organization_id=active_organization.id,
        agent_run_id=run.id,
        correlation_id=run.correlation_id,
        result=approval.status.value,
    )
    return _detail(db, run)


@router.post(
    "/runs/{run_id}/resume",
    response_model=ResumeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_run(
    request: Request,
    _origin: OriginChecked,
    run_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> ResumeResponse | JSONResponse:
    """Encola la reanudación con contexto mínimo; sin broker no hay cambio de estado."""
    run = _require_run(db, active_organization.id, run_id)
    request_id = _request_id(request)
    try:
        resume_agent_workflow.delay(
            str(active_organization.id),
            str(actor.id),
            _member.role.value,
            str(run.id),
            str(run.correlation_id),
        )
    except Exception:
        # Nunca propagar mensaje, URL ni traza del broker al cliente ni a logs.
        _log(
            "agent.resume_broker_failed",
            request_id=request_id,
            organization_id=active_organization.id,
            agent_run_id=run.id,
            correlation_id=run.correlation_id,
            result="failed",
            error_code=_BROKER_CODE,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": _BROKER_CODE,
                    "message": "Cola no disponible; la ejecución no cambió de estado.",
                    "request_id": request_id,
                }
            },
        )
    _log(
        "agent.resume_queued",
        request_id=request_id,
        organization_id=active_organization.id,
        agent_run_id=run.id,
        correlation_id=run.correlation_id,
        result="queued",
    )
    return ResumeResponse(
        agent_run_id=run.id,
        status=run.status,
        queued=True,
        correlation_id=run.correlation_id,
    )


@router.post("/runs/{run_id}/cancel", response_model=AgentRunDetail)
def cancel_run(
    request: Request,
    _origin: OriginChecked,
    run_id: uuid.UUID,
    actor: CurrentUser,
    active_organization: CurrentOrganization,
    _member: WriteMember,
    db: DbDependency,
) -> AgentRunDetail:
    """Cancela el run vivo; los estados terminales no se reescriben ni se reauditan."""
    before = _require_run(db, active_organization.id, run_id).status
    try:
        agents_service.cancel_workflow(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            actor_role=_member.role,
            agent_run_id=run_id,
        )
    except AgentDomainError as exc:
        raise _http_error(exc) from None

    run = _require_run(db, active_organization.id, run_id)
    if before not in MATCHING_REVIEW_WORKFLOW.terminal_statuses:
        record_audit(
            db,
            organization_id=active_organization.id,
            actor_id=actor.id,
            action="agent.run_cancelled",
            resource_type=_RESOURCE_TYPE,
            resource_id=run.id,
        )
        db.commit()
        _log(
            "agent.run_cancelled",
            request_id=_request_id(request),
            organization_id=active_organization.id,
            agent_run_id=run.id,
            correlation_id=run.correlation_id,
            result=run.status.value,
        )
    return _detail(db, run)
