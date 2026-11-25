"""Servicio de los workflows `matching_review` y `recruitment_orchestration`.

Toda operación recibe el tenant de la sesión autenticada. El estado de dominio
vive en `AgentRun`; LangGraph solo aporta el grafo y su checkpoint aislado.
El workflow se elige explícitamente entre dos contratos; ninguna aprobación se
resuelve automáticamente: `resume_workflow` exige decisión persistida del actor.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy.orm import Session as DBSession

from app.agents.checkpoints import SQLAgentCheckpointSaver
from app.agents.contracts import (
    MATCHING_REVIEW_WORKFLOW,
    RECRUITMENT_ORCHESTRATION_WORKFLOW,
    WorkflowContract,
)
from app.agents.models import (
    AgentDomainError,
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentTenantMismatchError,
    Approval,
    ApprovalStatus,
    thread_id_for,
)
from app.agents.orchestrator import (
    build_orchestration_registry,
    build_recruitment_orchestration_graph,
    select_flow_from_persisted_facts,
)
from app.agents.repositories import (
    create_agent_event,
    create_approval,
    get_agent_run,
    get_agent_run_by_idempotency_key,
    get_approval,
    get_or_create_agent_run,
    list_agent_events,
    list_approvals_for_run,
    list_checkpoints,
    set_agent_run_output,
    update_agent_run_status,
)
from app.agents.repositories import (
    decide_approval as persist_approval_decision,
)
from app.agents.schemas import workflow_state
from app.agents.tools import ToolRegistry
from app.agents.workflow import (
    WorkflowDependencies,
    build_config,
    build_matching_review_graph,
    build_workflow_registry,
)
from app.assessment.context import resolve_application
from app.db.session import SessionLocal
from app.identity.models import MembershipRole, User, UserStatus
from app.identity.repositories import get_membership
from app.llm.provider import LLMProvider
from app.llm.registry import get_llm_provider

_ALL_ROLES = frozenset(set(MembershipRole))
_WRITE_ROLES = frozenset(
    {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.RECRUITER}
)
_STATUS_EVENTS = {
    AgentRunStatus.COMPLETED: AgentEventType.RUN_COMPLETED,
    AgentRunStatus.FAILED: AgentEventType.RUN_FAILED,
    AgentRunStatus.CANCELLED: AgentEventType.RUN_CANCELLED,
    AgentRunStatus.TIMED_OUT: AgentEventType.RUN_TIMED_OUT,
}
_SAFE_STATE_KEYS = (
    "errors",
    "requirement_ids",
    "evaluation_statuses",
    "evidence_refs",
    "needs_review",
    "job_id",
    "job_version_id",
    "candidate_id",
    "selected_flow",
    "delegated_run_id",
    "delegated_guide_id",
    "approval_status",
    "approval_decided_by",
    "draft_id",
    "error_type",
)

GraphBuilder = Callable[[WorkflowDependencies], Any]
# Mapa EXPLÍCITO: dos contratos, dos grafos y dos registries; sin descubrimiento.
_WORKFLOW_CONTRACTS: dict[str, WorkflowContract] = {
    MATCHING_REVIEW_WORKFLOW.workflow: MATCHING_REVIEW_WORKFLOW,
    RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow: RECRUITMENT_ORCHESTRATION_WORKFLOW,
}
_GRAPH_BUILDERS: dict[str, GraphBuilder] = {
    MATCHING_REVIEW_WORKFLOW.workflow: build_matching_review_graph,
    RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow: build_recruitment_orchestration_graph,
}
_REGISTRY_BUILDERS: dict[str, Callable[[], ToolRegistry]] = {
    MATCHING_REVIEW_WORKFLOW.workflow: build_workflow_registry,
    RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow: build_orchestration_registry,
}


def _contract(workflow: str) -> WorkflowContract:
    try:
        return _WORKFLOW_CONTRACTS[workflow]
    except KeyError as exc:
        raise AgentDomainError("unknown_workflow") from exc


def _contract_for_run(run: AgentRun) -> WorkflowContract:
    return _contract(run.workflow)


def _as_uuid(value: object, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise AgentDomainError(code) from exc


def _role(value: MembershipRole | str) -> MembershipRole:
    if isinstance(value, MembershipRole):
        return value
    try:
        return MembershipRole(value)
    except ValueError as exc:
        raise AgentDomainError("invalid_role") from exc


def _require_actor(
    db: DBSession,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    *,
    allowed_roles: frozenset[MembershipRole] = _ALL_ROLES,
) -> tuple[User, MembershipRole]:
    membership = get_membership(db, actor_id, organization_id)
    if membership is None:
        raise AgentTenantMismatchError("Actor no disponible para la organización")
    role = _role(actor_role)
    if membership.role is not role or role not in allowed_roles:
        raise AgentDomainError("permission_denied")
    user = db.get(User, actor_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise AgentDomainError("permission_denied")
    return user, role


def _require_run(
    db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> AgentRun:
    run = get_agent_run(db, organization_id, agent_run_id)
    if run is None:
        raise AgentTenantMismatchError("Ejecución no disponible para la organización")
    return run


def _checkpointer(
    checkpointer: BaseCheckpointSaver[str] | None,
) -> BaseCheckpointSaver[str]:
    return checkpointer if checkpointer is not None else SQLAgentCheckpointSaver(SessionLocal)


def _dependencies(
    db: DBSession,
    run: AgentRun,
    *,
    actor_role: MembershipRole,
    provider: LLMProvider | None,
    checkpointer: BaseCheckpointSaver[str] | None,
    registry: ToolRegistry | None,
) -> WorkflowDependencies:
    contract = _contract_for_run(run)
    return WorkflowDependencies(
        db=db,
        organization_id=run.organization_id,
        actor_id=run.actor_id,
        actor_role=actor_role,
        correlation_id=run.correlation_id,
        agent_run_id=run.id,
        idempotency_key=run.idempotency_key,
        registry=registry if registry is not None else _REGISTRY_BUILDERS[contract.workflow](),
        provider=provider if provider is not None else get_llm_provider(),
        checkpointer=_checkpointer(checkpointer),
    )


def _config(run: AgentRun) -> RunnableConfig:
    return build_config(organization_id=run.organization_id, agent_run_id=run.id)


def _event_payload(
    run: AgentRun, *, correlation_id: uuid.UUID, **fields: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "organization_id": str(run.organization_id),
        "agent_run_id": str(run.id),
        "correlation_id": str(correlation_id),
    }
    payload.update(fields)
    return payload


def _emit(
    db: DBSession,
    run: AgentRun,
    event_type: AgentEventType,
    payload: dict[str, object],
    *,
    correlation_id: uuid.UUID,
) -> None:
    safe = _event_payload(run, correlation_id=correlation_id, **payload)
    safe.setdefault("node", "")
    safe.setdefault("duration_ms", 0)
    safe.setdefault("error_type", None)
    create_agent_event(
        db,
        organization_id=run.organization_id,
        agent_run_id=run.id,
        event_type=event_type,
        payload=safe,
        correlation_id=correlation_id,
    )


def _status(value: object) -> AgentRunStatus:
    try:
        return AgentRunStatus(str(value))
    except ValueError as exc:
        raise AgentDomainError("invalid_run_status") from exc


def _invoke(
    deps: WorkflowDependencies,
    config: RunnableConfig,
    payload: Mapping[str, object] | Command[Any],
    *,
    workflow: str,
) -> tuple[Mapping[str, object], Any]:
    graph = _GRAPH_BUILDERS[_contract(workflow).workflow](deps)
    try:
        result = graph.invoke(payload, config)
    except GraphInterrupt:
        result = cast(Mapping[str, object], graph.get_state(config).values)
    return cast(Mapping[str, object], result), graph


def _has_interrupt(
    graph: Any, config: RunnableConfig, result: Mapping[str, object]
) -> bool:
    if result.get("__interrupt__"):
        return True
    try:
        return bool(getattr(graph.get_state(config), "interrupts", ()))
    except Exception:
        return False


def _apply_terminal(
    db: DBSession,
    run: AgentRun,
    state: Mapping[str, object],
    *,
    correlation_id: uuid.UUID,
) -> AgentRunStatus:
    contract = _contract_for_run(run)
    status = _status(state.get("status"))
    if status not in contract.terminal_statuses:
        return status
    update_agent_run_status(db, run, status)
    event_type = _STATUS_EVENTS[status]
    errors = cast(list[dict[str, object]], state.get("errors") or [])
    last_error = errors[-1] if errors else None
    raw_duration = last_error.get("duration_ms") if last_error else None
    duration_ms = raw_duration if isinstance(raw_duration, int) else 0
    raw_attempts = last_error.get("attempts") if last_error else None
    attempts = raw_attempts if isinstance(raw_attempts, int) and raw_attempts >= 0 else 0
    _emit(
        db,
        run,
        event_type,
        {
            "node": contract.nodes[-1].name.value,
            "status": status.value,
            "duration_ms": duration_ms,
            "attempts": attempts,
            "error_type": str(state.get("error_type") or "") or None,
            "draft_id": str(state.get("draft_id") or "") or None,
            "delegated_run_id": str(state.get("delegated_run_id") or "") or None,
            "delegated_guide_id": str(state.get("delegated_guide_id") or "") or None,
        },
        correlation_id=correlation_id,
    )
    _emit(
        db,
        run,
        AgentEventType.CHECKPOINT_SAVED,
        {"thread_id": thread_id_for(run.organization_id, run.id)},
        correlation_id=correlation_id,
    )
    draft_id = state.get("draft_id")
    delegated_run_id = state.get("delegated_run_id")
    delegated_guide_id = state.get("delegated_guide_id")
    if status is AgentRunStatus.COMPLETED and draft_id:
        set_agent_run_output(db, run, f"draft:{draft_id}")
    elif status is AgentRunStatus.COMPLETED and delegated_run_id:
        set_agent_run_output(db, run, f"child:{delegated_run_id}")
    elif status is AgentRunStatus.COMPLETED and delegated_guide_id:
        set_agent_run_output(db, run, f"guide:{delegated_guide_id}")
    return status


def _view(
    db: DBSession,
    run: AgentRun,
    *,
    actor_role: MembershipRole,
    provider: LLMProvider | None,
    checkpointer: BaseCheckpointSaver[str] | None,
    registry: ToolRegistry | None,
) -> dict[str, object]:
    deps = _dependencies(
        db,
        run,
        actor_role=actor_role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )
    config = _config(run)
    state: Mapping[str, object] = {}
    next_nodes: tuple[str, ...] = ()
    try:
        graph = _GRAPH_BUILDERS[_contract_for_run(run).workflow](deps)
        snapshot = graph.get_state(config)
        state = cast(Mapping[str, object], snapshot.values)
        next_nodes = tuple(str(node) for node in snapshot.next)
    except Exception:
        state = {}
    events = list_agent_events(db, run.organization_id, run.id, limit=100)
    approvals = list_approvals_for_run(db, run.organization_id, run.id)
    latest = approvals[-1] if approvals else None
    draft_id = state.get("draft_id")
    if not draft_id and run.output_ref and run.output_ref.startswith("draft:"):
        draft_id = run.output_ref.split(":", 1)[1]
    safe_state: dict[str, object] = {
        key: state[key] for key in _SAFE_STATE_KEYS if key in state
    }
    return {
        "agent_run_id": str(run.id),
        "organization_id": str(run.organization_id),
        "workflow": run.workflow,
        "version": run.version,
        "status": run.status.value,
        "thread_id": thread_id_for(run.organization_id, run.id),
        "approval_id": str(latest.id) if latest is not None else None,
        "approval_status": latest.status.value if latest is not None else None,
        "approval_decided_by": str(latest.decided_by) if latest and latest.decided_by else None,
        "draft_id": str(draft_id) if draft_id else None,
        "error_type": str(state.get("error_type") or "") or None,
        "next_nodes": list(next_nodes),
        "checkpoints": len(
            list_checkpoints(
                db,
                run.organization_id,
                thread_id_for(run.organization_id, run.id),
                "",
            )
        ),
        "state": safe_state,
        "events": [
            {
                "event_type": event.event_type.value,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


def start_workflow(
    db: DBSession,
    *,
    organization_id: uuid.UUID | str,
    actor_id: uuid.UUID | str,
    actor_role: MembershipRole | str,
    application_id: uuid.UUID | str,
    idempotency_key: str,
    workflow: str = MATCHING_REVIEW_WORKFLOW.workflow,
    correlation_id: uuid.UUID | None = None,
    provider: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, object]:
    """Crea una ejecución idempotente, valida el tenant y corre hasta el HITL real."""
    contract = _contract(workflow)
    org_id = _as_uuid(organization_id, "invalid_context")
    actor = _as_uuid(actor_id, "invalid_context")
    application = _as_uuid(application_id, "invalid_context")
    user, role = _require_actor(
        db, org_id, actor, actor_role, allowed_roles=_WRITE_ROLES
    )
    resolved = resolve_application(db, org_id, application)
    if resolved is None:
        raise AgentTenantMismatchError("Postulación no disponible para la organización")
    if not idempotency_key.strip() or len(idempotency_key) > 100:
        raise AgentDomainError("invalid_idempotency_key")
    existing = get_agent_run_by_idempotency_key(db, org_id, idempotency_key)
    if existing is not None:
        if existing.workflow != contract.workflow:
            raise AgentDomainError("idempotency_workflow_conflict")
        return _view(
            db,
            existing,
            actor_role=role,
            provider=provider,
            checkpointer=checkpointer,
            registry=registry,
        )

    is_orchestration = contract is RECRUITMENT_ORCHESTRATION_WORKFLOW
    selected_flow: str | None = None
    if is_orchestration:
        selected_flow = select_flow_from_persisted_facts(db, org_id, application)
    correlation = correlation_id or uuid.uuid4()
    run = get_or_create_agent_run(
        db,
        organization_id=org_id,
        workflow=contract.workflow,
        version=contract.version,
        idempotency_key=idempotency_key,
        correlation_id=correlation,
        actor_id=user.id,
        input_ref=str(application),
    )
    approval_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    approval_payload: dict[str, object] = {
        "action_type": contract.approval_action_type,
        "application_id": str(application),
        "requested_by": str(user.id),
        "requested_at": datetime.now(UTC).isoformat(),
        "idempotency_hash": approval_hash,
    }
    if selected_flow is not None:
        approval_payload["selected_flow"] = selected_flow
    approval = create_approval(
        db,
        organization_id=org_id,
        agent_run_id=run.id,
        action_type=contract.approval_action_type,
        payload=approval_payload,
    )
    _emit(
        db,
        run,
        AgentEventType.RUN_CREATED,
        {"workflow": run.workflow, "version": run.version},
        correlation_id=correlation,
    )
    _emit(
        db,
        run,
        AgentEventType.APPROVAL_REQUESTED,
        {"approval_id": str(approval.id), "action_type": contract.approval_action_type},
        correlation_id=correlation,
    )
    update_agent_run_status(db, run, AgentRunStatus.RUNNING)
    _emit(
        db,
        run,
        AgentEventType.RUN_STARTED,
        {"node": contract.nodes[0].name.value},
        correlation_id=correlation,
    )
    db.commit()

    deps = _dependencies(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )
    config = _config(run)
    initial: dict[str, object] = {
        **workflow_state(
            organization_id=org_id,
            actor_id=user.id,
            correlation_id=correlation,
            agent_run_id=run.id,
            idempotency_key=run.idempotency_key,
            status=AgentRunStatus.RUNNING,
        ),
        "application_id": str(application),
        "approval_id": str(approval.id),
    }
    if is_orchestration:
        _, job, candidate, version = resolved
        initial.update(
            {
                "job_id": str(job.id),
                "job_version_id": str(version.id),
                "candidate_id": str(candidate.id),
                "selected_flow": selected_flow,
                "delegated_run_id": None,
                "delegated_guide_id": None,
            }
        )
    result, graph = _invoke(deps, config, initial, workflow=contract.workflow)
    if _has_interrupt(graph, config, result):
        update_agent_run_status(db, run, AgentRunStatus.WAITING_APPROVAL)
        _emit(
            db,
            run,
            AgentEventType.RUN_WAITING_APPROVAL,
            {
                "approval_id": str(approval.id),
                "node": contract.interrupt_before_effects.value,
            },
            correlation_id=correlation,
        )
        _emit(
            db,
            run,
            AgentEventType.GRAPH_INTERRUPTED,
            {"node": contract.interrupt_before_effects.value},
            correlation_id=correlation,
        )
        _emit(
            db,
            run,
            AgentEventType.CHECKPOINT_SAVED,
            {"thread_id": thread_id_for(org_id, run.id)},
            correlation_id=correlation,
        )
    else:
        _apply_terminal(db, run, result, correlation_id=correlation)
    db.commit()
    return _view(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )


def inspect_workflow(
    db: DBSession,
    *,
    organization_id: uuid.UUID | str,
    actor_id: uuid.UUID | str,
    actor_role: MembershipRole | str,
    agent_run_id: uuid.UUID | str,
    provider: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, object]:
    """Inspecciona un run del tenant; valida pertenencia antes de tocar el checkpoint."""
    org_id = _as_uuid(organization_id, "invalid_context")
    actor = _as_uuid(actor_id, "invalid_context")
    run_id = _as_uuid(agent_run_id, "invalid_context")
    _, role = _require_actor(db, org_id, actor, actor_role)
    run = _require_run(db, org_id, run_id)
    return _view(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )


def decide_approval(
    db: DBSession,
    *,
    organization_id: uuid.UUID | str,
    actor_id: uuid.UUID | str,
    actor_role: MembershipRole | str,
    agent_run_id: uuid.UUID | str,
    approval_id: uuid.UUID | str,
    decision: ApprovalStatus | str,
    provider: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, object]:
    """Persiste la decisión humana; nunca reanuda el grafo por su cuenta."""
    org_id = _as_uuid(organization_id, "invalid_context")
    actor = _as_uuid(actor_id, "invalid_context")
    run_id = _as_uuid(agent_run_id, "invalid_context")
    approval_uuid = _as_uuid(approval_id, "invalid_context")
    user, role = _require_actor(
        db, org_id, actor, actor_role, allowed_roles=_WRITE_ROLES
    )
    run = _require_run(db, org_id, run_id)
    approval = get_approval_for_decision(db, org_id, approval_uuid, run_id)
    try:
        target = decision if isinstance(decision, ApprovalStatus) else ApprovalStatus(decision)
    except ValueError as exc:
        raise AgentDomainError("invalid_decision") from exc
    if target is ApprovalStatus.PENDING:
        raise AgentDomainError("invalid_decision")
    persist_approval_decision(
        db,
        approval,
        decision=target,
        decided_by=user.id,
        decided_at=datetime.now(UTC),
    )
    _emit(
        db,
        run,
        AgentEventType.APPROVAL_RESOLVED,
        {
            "approval_id": str(approval.id),
            "decision": target.value,
            "decided_by": str(user.id),
        },
        correlation_id=run.correlation_id,
    )
    db.commit()
    return _view(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )


def get_approval_for_decision(
    db: DBSession,
    organization_id: uuid.UUID,
    approval_id: uuid.UUID,
    agent_run_id: uuid.UUID,
) -> Approval:
    """Lee una aprobación del tenant solo si pertenece a esa ejecución."""
    approval = get_approval(db, organization_id, approval_id)
    if approval is None or approval.agent_run_id != agent_run_id:
        raise AgentTenantMismatchError("Aprobación no disponible para la organización")
    return approval


def resume_workflow(
    db: DBSession,
    *,
    organization_id: uuid.UUID | str,
    actor_id: uuid.UUID | str,
    actor_role: MembershipRole | str,
    agent_run_id: uuid.UUID | str,
    provider: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, object]:
    """Reanuda solo con aprobación resuelta por el actor: jamás autoaprueba."""
    org_id = _as_uuid(organization_id, "invalid_context")
    actor = _as_uuid(actor_id, "invalid_context")
    run_id = _as_uuid(agent_run_id, "invalid_context")
    _, role = _require_actor(
        db, org_id, actor, actor_role, allowed_roles=_WRITE_ROLES
    )
    run = _require_run(db, org_id, run_id)
    contract = _contract_for_run(run)
    if run.status in contract.terminal_statuses:
        return _view(
            db,
            run,
            actor_role=role,
            provider=provider,
            checkpointer=checkpointer,
            registry=registry,
        )
    if run.status is not AgentRunStatus.WAITING_APPROVAL:
        raise AgentDomainError("workflow_not_waiting_approval")
    approvals = list_approvals_for_run(db, org_id, run.id)
    resolved = [
        item
        for item in approvals
        if item.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)
        and item.action_type == contract.approval_action_type
    ]
    if not resolved:
        raise AgentDomainError("approval_pending")
    approval = resolved[-1]
    if approval.decided_by != actor:
        raise AgentDomainError("approval_actor_mismatch")

    update_agent_run_status(db, run, AgentRunStatus.RUNNING)
    _emit(
        db,
        run,
        AgentEventType.RUN_STARTED,
        {
            "node": contract.interrupt_before_effects.value,
            "resumed": True,
            "decision": str(approval.status.value),
        },
        correlation_id=run.correlation_id,
    )
    db.commit()
    deps = _dependencies(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )
    config = _config(run)
    command: Command[Any] = Command(
        resume={
            "decision": approval.status.value,
            "approval_id": str(approval.id),
            "decided_by": str(actor),
        }
    )
    result, _ = _invoke(deps, config, command, workflow=contract.workflow)
    _apply_terminal(db, run, result, correlation_id=run.correlation_id)
    db.commit()
    return _view(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )


def cancel_workflow(
    db: DBSession,
    *,
    organization_id: uuid.UUID | str,
    actor_id: uuid.UUID | str,
    actor_role: MembershipRole | str,
    agent_run_id: uuid.UUID | str,
    provider: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, object]:
    """Cancela una ejecución viva; los estados terminales no se reescriben."""
    org_id = _as_uuid(organization_id, "invalid_context")
    actor = _as_uuid(actor_id, "invalid_context")
    run_id = _as_uuid(agent_run_id, "invalid_context")
    _, role = _require_actor(
        db, org_id, actor, actor_role, allowed_roles=_WRITE_ROLES
    )
    run = _require_run(db, org_id, run_id)
    contract = _contract_for_run(run)
    if run.status not in contract.terminal_statuses:
        update_agent_run_status(db, run, AgentRunStatus.CANCELLED)
        _emit(
            db,
            run,
            AgentEventType.RUN_CANCELLED,
            {"node": "manual", "status": AgentRunStatus.CANCELLED.value},
            correlation_id=run.correlation_id,
        )
        db.commit()
    return _view(
        db,
        run,
        actor_role=role,
        provider=provider,
        checkpointer=checkpointer,
        registry=registry,
    )
