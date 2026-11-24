"""Grafo `recruitment_orchestration`: selección acotada y HITL antes de delegar.

El orquestador no interpreta documentos: decide por hechos persistidos, pide
aprobación real y solo entonces delega en un flujo especializado. El checkpoint
contiene identificadores y estados validados; nunca CV, secretos, prompts ni
chain-of-thought. Las únicas tools autorizadas son las del contrato, definidas
en el registry existente.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any, Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy.orm import Session as DBSession

from app.agents.contracts import (
    MATCHING_REVIEW_WORKFLOW,
    RECRUITMENT_ORCHESTRATION_WORKFLOW,
    OrchestrationNode,
)
from app.agents.models import AgentDomainError, AgentRunStatus, ApprovalStatus
from app.agents.schemas import WorkflowState
from app.agents.tools import (
    ToolDefinition,
    ToolInvocationError,
    ToolRegistry,
    build_default_registry,
)
from app.agents.workflow import (
    WorkflowDependencies,
    WorkflowNodeError,
    _SanitizedCheckpointer,
)
from app.assessment.context import resolve_application
from app.assessment.repositories import count_assessments
from app.interviews import service as interviews_service
from app.interviews.models import InterviewDomainError, InterviewTenantMismatchError
from app.interviews.repositories import count_guides
from app.llm.provider import ProviderError

_APPROVED = ApprovalStatus.APPROVED.value
_REJECTED = ApprovalStatus.REJECTED.value
SelectedFlow = Literal["matching_review", "interview_guide", "review_only"]
_FLOWS: frozenset[str] = frozenset(
    {"matching_review", "interview_guide", "review_only"}
)


class OrchestrationState(WorkflowState, total=False):
    """Estado mínimo y serializable del grafo del orquestador."""

    application_id: str
    job_id: str
    job_version_id: str
    candidate_id: str
    selected_flow: SelectedFlow
    delegated_run_id: str | None
    delegated_guide_id: str | None
    approval_id: str
    approval_status: str
    error_type: str


def _as_uuid(value: object, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise WorkflowNodeError(code) from exc


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _error_type(exc: Exception) -> str:
    if isinstance(exc, WorkflowNodeError):
        return exc.code
    if isinstance(exc, ToolInvocationError):
        return str(exc.code.value)
    if isinstance(exc, ProviderError):
        return exc.code
    if isinstance(exc, ValidationError):
        return "invalid_provider_output"
    if isinstance(exc, InterviewTenantMismatchError):
        return "tenant_mismatch"
    if isinstance(exc, (InterviewDomainError, AgentDomainError)):
        return "delegation_rejected"
    if isinstance(exc, TimeoutError):
        return "timeout"
    return "internal_error"


def _failure(
    state: Mapping[str, object],
    *,
    node: OrchestrationNode,
    error_type: str,
    attempts: int,
    duration_ms: int,
    status: AgentRunStatus = AgentRunStatus.FAILED,
) -> dict[str, object]:
    errors = list(cast(list[dict[str, object]], state.get("errors") or []))
    errors.append(
        {
            "node": node.value,
            "error_type": error_type,
            "attempts": attempts,
            "duration_ms": duration_ms,
        }
    )
    return {"status": status, "error_type": error_type, "errors": errors}


NodeOperation = Callable[
    [OrchestrationState, WorkflowDependencies], dict[str, object]
]


def _guarded(
    name: OrchestrationNode,
    operation: NodeOperation,
    deps: WorkflowDependencies,
) -> Callable[[OrchestrationState], dict[str, object]]:
    """Aplica timeout y un único reintento; no atrapa interrupciones reales."""

    def run(state: OrchestrationState) -> dict[str, object]:
        contract = RECRUITMENT_ORCHESTRATION_WORKFLOW.node(name)
        max_attempts = contract.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            started = monotonic()
            try:
                update = operation(state, deps)
            except Exception as exc:
                duration = max(0, int((monotonic() - started) * 1000))
                if attempt < max_attempts:
                    continue
                return _failure(
                    state,
                    node=name,
                    error_type=_error_type(exc),
                    attempts=attempt,
                    duration_ms=duration,
                )
            duration = max(0, int((monotonic() - started) * 1000))
            if duration > contract.timeout_seconds * 1000:
                if attempt < max_attempts:
                    continue
                return _failure(
                    state,
                    node=name,
                    error_type="timeout",
                    attempts=attempt,
                    duration_ms=duration,
                    status=AgentRunStatus.TIMED_OUT,
                )
            return update
        return _failure(
            state,
            node=name,
            error_type="retries_exhausted",
            attempts=max_attempts,
            duration_ms=0,
        )

    return run


def _bind_deps(
    operation: NodeOperation, deps: WorkflowDependencies
) -> Callable[[OrchestrationState], dict[str, object]]:
    def run(state: OrchestrationState) -> dict[str, object]:
        return operation(state, deps)

    return run


def select_flow_from_persisted_facts(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
) -> SelectedFlow:
    """Determina el flujo solo con hechos persistidos del tenant; sin CV ni LLM."""
    has_assessment = count_assessments(
        db, organization_id, application_id=application_id
    ) > 0
    has_guide = count_guides(db, organization_id, application_id=application_id) > 0
    if not has_assessment:
        return "matching_review"
    if not has_guide:
        return "interview_guide"
    return "review_only"


def _receive_task(
    state: OrchestrationState, deps: WorkflowDependencies
) -> dict[str, object]:
    """Revalida tenant, actor e identificadores antes de cualquier decisión."""
    application_id = _as_uuid(state.get("application_id"), "invalid_context")
    _as_uuid(state.get("actor_id"), "invalid_context")
    _as_uuid(state.get("correlation_id"), "invalid_context")
    resolved = resolve_application(deps.db, deps.organization_id, application_id)
    if resolved is None:
        raise WorkflowNodeError("tenant_mismatch")
    _, job, candidate, version = resolved
    expected = {
        "job_id": job.id,
        "candidate_id": candidate.id,
        "job_version_id": version.id,
    }
    for key, value in expected.items():
        raw = state.get(key)
        if raw is not None and str(raw) != str(value):
            raise WorkflowNodeError("tenant_mismatch")
    return {
        "application_id": str(application_id),
        "job_id": str(job.id),
        "candidate_id": str(candidate.id),
        "job_version_id": str(version.id),
    }


def _select_flow(
    state: OrchestrationState, deps: WorkflowDependencies
) -> dict[str, object]:
    application_id = _as_uuid(state.get("application_id"), "invalid_context")
    return {
        "selected_flow": select_flow_from_persisted_facts(
            deps.db, deps.organization_id, application_id
        )
    }


def _approval_payload(state: Mapping[str, object]) -> dict[str, object]:
    approval_id = state.get("approval_id")
    application_id = state.get("application_id")
    selected_flow = state.get("selected_flow")
    if (
        not approval_id
        or not _is_uuid(str(approval_id))
        or not application_id
        or not _is_uuid(str(application_id))
        or selected_flow not in _FLOWS
    ):
        raise WorkflowNodeError("invalid_approval_request")
    return {
        "approval_id": str(approval_id),
        "action_type": RECRUITMENT_ORCHESTRATION_WORKFLOW.approval_action_type,
        "application_id": str(application_id),
        "selected_flow": str(selected_flow),
        "node": OrchestrationNode.REQUEST_APPROVAL.value,
    }


def _request_approval(
    state: OrchestrationState, deps: WorkflowDependencies
) -> dict[str, object]:
    del deps
    payload = _approval_payload(state)
    response = interrupt(payload)
    decision = ""
    decided_by = ""
    approved_id = ""
    if isinstance(response, Mapping):
        decision = str(response.get("decision") or "")
        decided_by = str(response.get("decided_by") or "")
        approved_id = str(response.get("approval_id") or "")
    if (
        decision not in (_APPROVED, _REJECTED)
        or approved_id != payload["approval_id"]
        or not _is_uuid(decided_by)
    ):
        return _failure(
            state,
            node=OrchestrationNode.REQUEST_APPROVAL,
            error_type="invalid_approval_response",
            attempts=1,
            duration_ms=0,
        )
    return {
        "approval_status": decision,
        "status": AgentRunStatus.RUNNING,
    }


def _delegate_matching(
    state: OrchestrationState, deps: WorkflowDependencies
) -> str:
    # Import local: el servicio construye este grafo; el ciclo se evita en el nodo.
    from app.agents import service as agents_service

    application_id = _as_uuid(state.get("application_id"), "invalid_context")
    child_key = f"orchestration-child:{deps.agent_run_id}"
    child = agents_service.start_workflow(
        deps.db,
        organization_id=deps.organization_id,
        actor_id=deps.actor_id,
        actor_role=deps.actor_role,
        application_id=application_id,
        idempotency_key=child_key,
        correlation_id=deps.correlation_id,
        provider=deps.provider,
        checkpointer=deps.checkpointer,
        workflow=MATCHING_REVIEW_WORKFLOW.workflow,
    )
    return str(child["agent_run_id"])


def _delegate_interview_guide(
    state: OrchestrationState, deps: WorkflowDependencies
) -> str:
    application_id = _as_uuid(state.get("application_id"), "invalid_context")
    result = interviews_service.generate_guide(
        deps.db,
        organization_id=deps.organization_id,
        actor_id=deps.actor_id,
        actor_role=deps.actor_role,
        application_id=application_id,
        provider=deps.provider,
    )
    return str(_as_uuid(result.get("guide_id"), "invalid_tool_result"))


def _delegate(
    state: OrchestrationState, deps: WorkflowDependencies
) -> dict[str, object]:
    """Efecto sensible: solo se ejecuta con aprobación persistida y resuelta."""
    if state.get("approval_status") != _APPROVED or state.get("error_type"):
        raise WorkflowNodeError("approval_missing")
    selected = state.get("selected_flow")
    if selected == "matching_review":
        return {
            "delegated_run_id": _delegate_matching(state, deps),
            "delegated_guide_id": None,
        }
    if selected == "interview_guide":
        return {
            "delegated_run_id": None,
            "delegated_guide_id": _delegate_interview_guide(state, deps),
        }
    if selected == "review_only":
        return {"delegated_run_id": None, "delegated_guide_id": None}
    raise WorkflowNodeError("invalid_selected_flow")


def _finalize(
    state: OrchestrationState, deps: WorkflowDependencies
) -> dict[str, object]:
    del deps
    error_type = state.get("error_type")
    if error_type:
        raw_status = state.get("status")
        status = (
            raw_status
            if raw_status in (AgentRunStatus.FAILED, AgentRunStatus.TIMED_OUT)
            else AgentRunStatus.FAILED
        )
        return {"status": status}
    decision = state.get("approval_status")
    if decision == _REJECTED:
        return {"status": AgentRunStatus.CANCELLED}
    if decision != _APPROVED:
        return _failure(
            state,
            node=OrchestrationNode.FINALIZE,
            error_type="invalid_approval_response",
            attempts=1,
            duration_ms=0,
        )
    selected = state.get("selected_flow")
    if selected == "matching_review" and not state.get("delegated_run_id"):
        return _failure(
            state,
            node=OrchestrationNode.FINALIZE,
            error_type="delegation_missing",
            attempts=1,
            duration_ms=0,
        )
    if selected == "interview_guide" and not state.get("delegated_guide_id"):
        return _failure(
            state,
            node=OrchestrationNode.FINALIZE,
            error_type="delegation_missing",
            attempts=1,
            duration_ms=0,
        )
    return {"status": AgentRunStatus.COMPLETED}


def _route_after_approval(state: OrchestrationState) -> str:
    if state.get("error_type") or state.get("approval_status") != _APPROVED:
        return "finalize"
    return "delegate"


def _route_after_read(state: OrchestrationState) -> str:
    return "finalize" if state.get("error_type") else "continue"


def build_orchestration_registry() -> ToolRegistry:
    """Registry del orquestador: solo las tres tools de lectura del contrato."""
    default = build_default_registry()
    scoped = ToolRegistry()
    for name in sorted(RECRUITMENT_ORCHESTRATION_WORKFLOW.allowed_tools):
        definition = default.get(name)
        scoped.register(
            ToolDefinition(
                name=definition.name,
                handler=definition.handler,
                input_schema=definition.input_schema,
                allowed_workflows=frozenset(
                    {RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow}
                ),
                roles=definition.roles,
                timeout_seconds=definition.timeout_seconds,
                max_calls_per_run=definition.max_calls_per_run,
                is_write=definition.is_write,
            )
        )
    return scoped


def build_recruitment_orchestration_graph(deps: WorkflowDependencies) -> Any:
    """Compila el grafo con checkpoint tenant-scoped y edges deterministas."""
    builder: Any = StateGraph(OrchestrationState)
    builder.add_node(
        OrchestrationNode.RECEIVE_TASK.value,
        _guarded(OrchestrationNode.RECEIVE_TASK, _receive_task, deps),
    )
    builder.add_node(
        OrchestrationNode.SELECT_FLOW.value,
        _guarded(OrchestrationNode.SELECT_FLOW, _select_flow, deps),
    )
    builder.add_node(
        OrchestrationNode.REQUEST_APPROVAL.value,
        _bind_deps(_request_approval, deps),
    )
    builder.add_node(
        OrchestrationNode.DELEGATE.value,
        _guarded(OrchestrationNode.DELEGATE, _delegate, deps),
    )
    builder.add_node(
        OrchestrationNode.FINALIZE.value,
        _guarded(OrchestrationNode.FINALIZE, _finalize, deps),
    )

    builder.add_edge(START, OrchestrationNode.RECEIVE_TASK.value)
    builder.add_conditional_edges(
        OrchestrationNode.RECEIVE_TASK.value,
        _route_after_read,
        {
            "continue": OrchestrationNode.SELECT_FLOW.value,
            "finalize": OrchestrationNode.FINALIZE.value,
        },
    )
    builder.add_conditional_edges(
        OrchestrationNode.SELECT_FLOW.value,
        _route_after_read,
        {
            "continue": OrchestrationNode.REQUEST_APPROVAL.value,
            "finalize": OrchestrationNode.FINALIZE.value,
        },
    )
    builder.add_conditional_edges(
        OrchestrationNode.REQUEST_APPROVAL.value,
        _route_after_approval,
        {
            "delegate": OrchestrationNode.DELEGATE.value,
            "finalize": OrchestrationNode.FINALIZE.value,
        },
    )
    builder.add_edge(OrchestrationNode.DELEGATE.value, OrchestrationNode.FINALIZE.value)
    builder.add_edge(OrchestrationNode.FINALIZE.value, END)
    checkpointer = (
        deps.checkpointer
        if isinstance(deps.checkpointer, _SanitizedCheckpointer)
        else _SanitizedCheckpointer(deps.checkpointer)
    )
    return builder.compile(checkpointer=checkpointer)


__all__ = [
    "OrchestrationState",
    "build_orchestration_registry",
    "build_recruitment_orchestration_graph",
    "select_flow_from_persisted_facts",
]
