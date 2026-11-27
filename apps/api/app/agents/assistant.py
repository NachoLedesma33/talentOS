"""Grafo `workspace_assistant`: respuestas verificables y acciones propuestas.

El asistente no ejecuta SQL libre, navegación arbitraria ni efectos de dominio:
toda lectura sale del registry acotado, la salida del proveedor se valida contra
un esquema cerrado y las acciones se contrastan con capacidades, esquemas de
formulario, rol y evidencia confirmada. Antes de cualquier efecto hay
`interrupt`; el checkpoint conserva solo identificadores, estados y citas
acotadas, nunca el mensaje completo ni secretos (SDD §9.3, ADR-020).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.contracts import (
    WORKSPACE_ASSISTANT_WORKFLOW,
    AssistantAction,
    AssistantActionType,
    AssistantFormId,
    AssistantMessageResponse,
    AssistantNode,
    AssistantSurface,
    EvidenceRef,
    FieldOrigin,
)
from app.agents.models import AgentRunStatus, ApprovalStatus
from app.agents.schemas import WorkflowState, validate_safe_payload, workflow_state
from app.agents.tool_schemas import GetCandidateProfileInput, GetConfirmedDocumentTextInput
from app.agents.tools import EmptyInput, FormSchemaInput, ListWorkspaceInput
from app.agents.workflow import (
    WorkflowDependencies,
    WorkflowNodeError,
    _as_uuid,
    _error_type,
    _SanitizedCheckpointer,
    _tool_context,
)
from app.applications.repositories import get_application
from app.candidates.repositories import get_candidate
from app.documents.repositories import get_document
from app.identity.models import MembershipRole
from app.jobs.repositories import get_job

PROMPT_VERSION = "workspace-assistant-v1"
MAX_CITATIONS = 10
MAX_ACTIONS = 5
MAX_LIMITATIONS = 10
MAX_EVIDENCE = 20
_SAFE_ANSWER = "No pude verificar una respuesta con la información disponible."
_INJECTION_PATTERNS = (
    "ignore previous",
    "ignora instrucciones",
    "ignore instructions",
    "system prompt",
    "prompt del sistema",
    "revela tu prompt",
    "ejecuta sql",
    "run shell",
    "curl ",
)
_VIEWER_ACTIONS = frozenset(
    {AssistantActionType.EXPLAIN.value, AssistantActionType.NAVIGATE.value}
)


@dataclass(frozen=True)
class AssistantDependencies(WorkflowDependencies):
    """Dependencias del asistente; el mensaje crudo solo vive en memoria."""

    prompt_context: Mapping[str, object] = field(default_factory=dict)


class _StrictAssistantModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class DraftCitation(_StrictAssistantModel):
    document_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    quote: str = Field(min_length=1, max_length=300)
    page: int | None = Field(default=None, ge=1, le=500)


class DraftAction(_StrictAssistantModel):
    type: AssistantActionType
    form_id: AssistantFormId | None = None
    route: str | None = Field(default=None, max_length=200)
    patch: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=20
    )
    field_origins: dict[str, FieldOrigin] = Field(default_factory=dict, max_length=20)


class AssistantDraftOutput(_StrictAssistantModel):
    """Salida estricta del proveedor; dominio y permisos no dependen del LLM."""

    answer: str = Field(min_length=1, max_length=4000)
    citations: list[DraftCitation] = Field(default_factory=list, max_length=MAX_CITATIONS)
    actions: list[DraftAction] = Field(default_factory=list, max_length=MAX_ACTIONS)
    limitations: list[str] = Field(default_factory=list, max_length=MAX_LIMITATIONS)
    needs_review: bool = False


class AssistantState(WorkflowState, total=False):
    """Estado serializable y mínimo del asistente."""

    surface: str
    resource_ref: str | None
    resource_kind: str
    message_fingerprint: str
    history_count: int
    injection_detected: bool
    capabilities: dict[str, object]
    form_schemas: dict[str, dict[str, object]]
    tool_facts: dict[str, object]
    evidence: list[dict[str, object]]
    draft: dict[str, object]
    answer: str
    citations: list[dict[str, object]]
    proposed_actions: list[dict[str, object]]
    limitations: list[str]
    needs_review: bool
    unsupported_reason: str | None
    approval_id: str
    approval_status: str
    error_type: str


NodeOperation = Callable[[AssistantState, AssistantDependencies], dict[str, object]]


def _contains_injection(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _INJECTION_PATTERNS)


def initial_assistant_state(
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    correlation_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    idempotency_key: str,
    message: str,
    recent_messages: tuple[str, ...] = (),
    surface: AssistantSurface,
    resource_ref: uuid.UUID | None = None,
) -> AssistantState:
    """Estado inicial sin mensajes crudos: solo huella, superficie y recursos."""
    fingerprint_source = "\n".join((message, *recent_messages))
    state: AssistantState = {
        **workflow_state(
            organization_id=organization_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            agent_run_id=agent_run_id,
            idempotency_key=idempotency_key,
        ),
        "surface": surface.value,
        "resource_ref": None if resource_ref is None else str(resource_ref),
        "resource_kind": "",
        "message_fingerprint": hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest(),
        "history_count": len(recent_messages),
        "injection_detected": _contains_injection(fingerprint_source),
        "capabilities": {},
        "form_schemas": {},
        "tool_facts": {},
        "evidence": [],
        "draft": {},
        "answer": _SAFE_ANSWER,
        "citations": [],
        "proposed_actions": [],
        "limitations": [],
        "needs_review": False,
        "unsupported_reason": None,
        "approval_id": "",
        "approval_status": "",
        "error_type": "",
    }
    return state


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _resource_kind(
    state: AssistantState, deps: AssistantDependencies
) -> str:
    raw = state.get("resource_ref")
    if raw is None or raw == "":
        return ""
    resource_id = _as_uuid(raw, "not_available")
    if get_document(deps.db, deps.organization_id, resource_id) is not None:
        return "document"
    if get_candidate(deps.db, deps.organization_id, resource_id) is not None:
        return "candidate"
    if get_application(deps.db, deps.organization_id, resource_id) is not None:
        return "application"
    if get_job(deps.db, deps.organization_id, resource_id) is not None:
        return "job"
    raise WorkflowNodeError("not_available")


def _receive_request(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Revalida tenant, actor, correlación y superficie antes de cualquier lectura."""
    expected = {
        "organization_id": deps.organization_id,
        "actor_id": deps.actor_id,
        "correlation_id": deps.correlation_id,
        "agent_run_id": deps.agent_run_id,
    }
    for key, value in expected.items():
        if str(state.get(key) or "") != str(value):
            raise WorkflowNodeError("tenant_mismatch")
    surfaces = {surface.value for surface in AssistantSurface}
    if str(state.get("surface") or "") not in surfaces:
        raise WorkflowNodeError("invalid_context")
    if not str(state.get("message_fingerprint") or ""):
        raise WorkflowNodeError("invalid_context")
    return {
        "resource_kind": _resource_kind(state, deps),
        "status": AgentRunStatus.RUNNING,
    }


def _resolve_context(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Fija allowlists cerradas desde el registry; nunca desde texto del modelo."""
    del state
    ctx = _tool_context(deps)
    capabilities = deps.registry.invoke(ctx, "get_platform_capabilities", EmptyInput())
    raw_capabilities = capabilities.model_dump(mode="json")
    # Esquemas se consultan SOLO para formularios propuestos por la salida validada;
    # pedir los seis de antemano agotaba el límite por ejecución del registry.
    return {
        "capabilities": {
            "workflow": raw_capabilities.get("workflow"),
            "version": raw_capabilities.get("version"),
            "intents": raw_capabilities.get("intents"),
            "surfaces": raw_capabilities.get("surfaces"),
            "forms": raw_capabilities.get("forms"),
            "routes": raw_capabilities.get("routes"),
        },
        "form_schemas": {},
    }


def _bounded_jobs(result: object) -> list[dict[str, object]]:
    rows = cast(list[object], getattr(result, "jobs", []) or [])
    return [
        {
            "job_id": str(cast(Any, row).job_id),
            "status": str(cast(Any, row).status),
        }
        for row in rows[:10]
    ]


def _bounded_candidates(result: object) -> list[dict[str, object]]:
    rows = cast(list[object], getattr(result, "candidates", []) or [])
    return [
        {
            "candidate_id": str(cast(Any, row).candidate_id),
            "profile_status": str(cast(Any, row).profile_status),
        }
        for row in rows[:10]
    ]


def _retrieve_allowed_facts(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Solo hechos del tenant y citas confirmadas; sin texto libre del CV."""
    ctx = _tool_context(deps)
    summary = deps.registry.invoke(ctx, "get_workspace_summary", EmptyInput())
    jobs = deps.registry.invoke(ctx, "list_jobs", ListWorkspaceInput(limit=10))
    candidates = deps.registry.invoke(ctx, "list_candidates", ListWorkspaceInput(limit=10))
    applications = deps.registry.invoke(
        ctx, "list_applications", ListWorkspaceInput(limit=10)
    )
    facts: dict[str, object] = {
        "workspace": summary.model_dump(mode="json"),
        "jobs": _bounded_jobs(jobs),
        "candidates": _bounded_candidates(candidates),
        "applications": len(cast(list[object], getattr(applications, "applications", []))),
    }
    evidence: list[dict[str, object]] = []
    resource_kind = str(state.get("resource_kind") or "")
    raw_ref = state.get("resource_ref")
    if raw_ref and resource_kind in {"document", "candidate"}:
        resource_id = _as_uuid(str(raw_ref), "not_available")
        if resource_kind == "document":
            quotes = deps.registry.invoke(
                ctx,
                "get_confirmed_document_text",
                GetConfirmedDocumentTextInput(document_id=resource_id, limit=5),
            )
            for quote in cast(list[object], getattr(quotes, "quotes", []) or []):
                evidence.append(
                    {
                        "document_id": str(cast(Any, quote).document_id),
                        "candidate_id": "",
                        "page": int(cast(Any, quote).page),
                        "quote": str(cast(Any, quote).quote),
                    }
                )
        else:
            profile = deps.registry.invoke(
                ctx, "get_candidate_profile", GetCandidateProfileInput(candidate_id=resource_id)
            )
            for quote in cast(list[object], getattr(profile, "evidence", []) or []):
                evidence.append(
                    {
                        "document_id": str(cast(Any, quote).document_id),
                        "candidate_id": str(resource_id),
                        "page": int(cast(Any, quote).page),
                        "quote": str(cast(Any, quote).quote),
                    }
                )
    return {"tool_facts": facts, "evidence": evidence[:MAX_EVIDENCE]}


def _draft_response(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Proveedor determinista: el contexto está acotado y nunca incluye secretos."""
    context: dict[str, object] = {
        "prompt_version": PROMPT_VERSION,
        "message": str(deps.prompt_context.get("message") or ""),
        "surface": state.get("surface"),
        "history_count": state.get("history_count", 0),
        "facts": state.get("tool_facts") or {},
        "evidence": state.get("evidence") or [],
        "capabilities": state.get("capabilities") or {},
        "injection_detected": bool(state.get("injection_detected")),
    }
    raw = deps.provider.generate_structured_output(
        PROMPT_VERSION, AssistantDraftOutput, context
    )
    draft = AssistantDraftOutput.model_validate(raw)
    return {"draft": draft.model_dump(mode="json")}


def _allowed_evidence(state: AssistantState) -> set[tuple[str, str, str, int]]:
    allowed: set[tuple[str, str, str, int]] = set()
    for raw in cast(list[object], state.get("evidence") or []):
        if not isinstance(raw, Mapping):
            continue
        allowed.add(
            (
                str(raw.get("quote") or ""),
                str(raw.get("document_id") or ""),
                str(raw.get("candidate_id") or ""),
                int(cast(int, raw.get("page") or 0)),
            )
        )
    return allowed


def _validate_policy(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Contradice salida, capacidades, esquemas, rol y evidencia; sin efectos."""
    try:
        draft = AssistantDraftOutput.model_validate(state.get("draft") or {})
    except ValidationError:
        draft = AssistantDraftOutput(answer=_SAFE_ANSWER, needs_review=True)
    capabilities = cast(Mapping[str, object], state.get("capabilities") or {})
    allowed_intents = set(cast(list[str], capabilities.get("intents") or []))
    allowed_forms = set(cast(list[str], capabilities.get("forms") or []))
    allowed_routes = set(cast(list[str], capabilities.get("routes") or []))
    ctx = _tool_context(deps)
    schemas: dict[str, Mapping[str, object]] = {}
    allowed = _allowed_evidence(state)

    limitations = [item for item in draft.limitations[:MAX_LIMITATIONS]]
    needs_review = bool(draft.needs_review or state.get("injection_detected"))
    citations: list[EvidenceRef] = []
    for item in draft.citations[:MAX_CITATIONS]:
        key = (
            item.quote,
            "" if item.document_id is None else str(item.document_id),
            "" if item.candidate_id is None else str(item.candidate_id),
            item.page or 0,
        )
        if key not in allowed:
            needs_review = True
            continue
        citations.append(
            EvidenceRef(
                quote=item.quote,
                organization_id=deps.organization_id,
                document_id=item.document_id,
                candidate_id=item.candidate_id,
                page=item.page,
            )
        )

    actions: list[AssistantAction] = []
    for index, action_item in enumerate(draft.actions[:MAX_ACTIONS]):
        if action_item.type.value not in allowed_intents:
            needs_review = True
            continue
        if action_item.form_id is not None and action_item.form_id.value not in allowed_forms:
            needs_review = True
            continue
        if action_item.route is not None and action_item.route not in allowed_routes:
            needs_review = True
            continue
        if (
            deps.actor_role is MembershipRole.VIEWER
            and action_item.type.value not in _VIEWER_ACTIONS
        ):
            limitations.append("permission_denied")
            needs_review = True
            continue
        if action_item.form_id is None:
            schema: Mapping[str, object] = {}
        else:
            form_key = action_item.form_id.value
            if form_key not in schemas:
                result = deps.registry.invoke(
                    ctx, "get_form_schema", FormSchemaInput(form_id=action_item.form_id)
                )
                schemas[form_key] = cast(
                    Mapping[str, object], result.model_dump(mode="json")
                )
            schema = schemas[form_key]
        schema_fields = {
            str(field.get("name"))
            for field in cast(list[object], schema.get("fields") or [])
            if isinstance(field, Mapping) and field.get("name") is not None
        }
        if action_item.form_id is not None and not set(action_item.patch) <= schema_fields:
            needs_review = True
            continue
        if action_item.patch and set(action_item.patch) != set(action_item.field_origins):
            needs_review = True
            continue
        action_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"assistant-action:{deps.organization_id}:{deps.idempotency_key}:{index}",
        )
        try:
            actions.append(
                AssistantAction(
                    action_id=action_id,
                    type=action_item.type,
                    form_id=action_item.form_id,
                    route=action_item.route,
                    patch=action_item.patch,
                    field_origins=action_item.field_origins,
                    requires_confirmation=True,
                )
            )
        except (ValidationError, ValueError):
            needs_review = True
    unsupported = None
    if state.get("injection_detected") and not citations:
        unsupported = "unsupported_request"
    status = AgentRunStatus.WAITING_APPROVAL if actions else AgentRunStatus.COMPLETED
    return {
        # La salida cruda del proveedor no se conserva en el estado público/checkpoint final.
        "draft": {},
        "answer": draft.answer or _SAFE_ANSWER,
        "citations": [ref.model_dump(mode="json") for ref in citations],
        "proposed_actions": [action.model_dump(mode="json") for action in actions],
        "limitations": limitations[:MAX_LIMITATIONS],
        "needs_review": needs_review,
        "unsupported_reason": unsupported,
        "status": status,
        "approval_id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"assistant-approval:{deps.organization_id}:{deps.idempotency_key}",
            )
        ),
    }


def _propose_actions(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Interrupt real antes de cualquier efecto; la reanudación debe ser explícita."""
    actions = cast(list[object], state.get("proposed_actions") or [])
    if not actions:
        return {"status": AgentRunStatus.COMPLETED}
    payload = validate_safe_payload(
        {
            "workflow": WORKSPACE_ASSISTANT_WORKFLOW.workflow,
            "version": WORKSPACE_ASSISTANT_WORKFLOW.version,
            "node": AssistantNode.PROPOSE_ACTIONS.value,
            "action_type": WORKSPACE_ASSISTANT_WORKFLOW.approval_action_type,
            "approval_id": str(state.get("approval_id") or ""),
            "action_count": len(actions),
            "run_id": str(deps.agent_run_id),
        }
    )
    response = interrupt(payload)
    decision = ""
    decided_by = ""
    approval_id = ""
    if isinstance(response, Mapping):
        decision = str(response.get("decision") or "")
        decided_by = str(response.get("decided_by") or "")
        approval_id = str(response.get("approval_id") or "")
    if (
        decision not in (ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value)
        or approval_id != payload["approval_id"]
        or not _is_uuid(decided_by)
    ):
        return _failure(
            state,
            node=AssistantNode.PROPOSE_ACTIONS,
            error_type="invalid_approval_response",
            attempts=1,
            duration_ms=0,
        )
    if decision is ApprovalStatus.REJECTED.value:
        return {
            "approval_status": ApprovalStatus.REJECTED.value,
            "status": AgentRunStatus.CANCELLED,
        }
    return {
        "approval_status": ApprovalStatus.APPROVED.value,
        "status": AgentRunStatus.COMPLETED,
    }


def _failure(
    state: Mapping[str, object],
    *,
    node: AssistantNode,
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


def _guarded(
    name: AssistantNode, operation: NodeOperation, deps: AssistantDependencies
) -> Callable[[AssistantState], dict[str, object]]:
    """Timeout y reintentos del contrato; no atrapa interrupciones reales."""

    def run(state: AssistantState) -> dict[str, object]:
        contract = WORKSPACE_ASSISTANT_WORKFLOW.node(name)
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
    operation: NodeOperation, deps: AssistantDependencies
) -> Callable[[AssistantState], dict[str, object]]:
    def run(state: AssistantState) -> dict[str, object]:
        return operation(state, deps)

    return run


def _finalize(
    state: AssistantState, deps: AssistantDependencies
) -> dict[str, object]:
    """Cierra estados terminales y traduce fallos a límites verificables."""
    del deps
    error_type = str(state.get("error_type") or "")
    if error_type:
        status = (
            AgentRunStatus.TIMED_OUT
            if error_type == "timeout"
            else AgentRunStatus.FAILED
        )
        return {
            "status": status,
            "answer": _SAFE_ANSWER,
            "needs_review": True,
            "unsupported_reason": error_type[:300],
        }
    raw_status: object = state.get("status")
    if isinstance(raw_status, AgentRunStatus):
        return {"status": raw_status}
    if isinstance(raw_status, str):
        try:
            return {"status": AgentRunStatus(raw_status)}
        except ValueError:
            pass
    return _failure(
        state,
        node=AssistantNode.FINALIZE,
        error_type="invalid_run_status",
        attempts=1,
        duration_ms=0,
    )


def _route_after_read(state: AssistantState) -> str:
    return "finalize" if state.get("error_type") else "continue"


def _route_after_read_or_wait(state: AssistantState) -> str:
    if state.get("error_type"):
        return "finalize"
    return "continue"


def build_workspace_assistant_graph(deps: AssistantDependencies) -> Any:
    """Compila el grafo con checkpointer tenant-scoped y edges deterministas."""
    builder: Any = StateGraph(AssistantState)
    builder.add_node(
        AssistantNode.RECEIVE_REQUEST.value,
        _guarded(AssistantNode.RECEIVE_REQUEST, _receive_request, deps),
    )
    builder.add_node(
        AssistantNode.RESOLVE_CONTEXT.value,
        _guarded(AssistantNode.RESOLVE_CONTEXT, _resolve_context, deps),
    )
    builder.add_node(
        AssistantNode.RETRIEVE_ALLOWED_FACTS.value,
        _guarded(AssistantNode.RETRIEVE_ALLOWED_FACTS, _retrieve_allowed_facts, deps),
    )
    builder.add_node(
        AssistantNode.DRAFT_RESPONSE.value,
        _guarded(AssistantNode.DRAFT_RESPONSE, _draft_response, deps),
    )
    builder.add_node(
        AssistantNode.VALIDATE_POLICY.value,
        _guarded(AssistantNode.VALIDATE_POLICY, _validate_policy, deps),
    )
    builder.add_node(
        AssistantNode.PROPOSE_ACTIONS.value,
        _bind_deps(_propose_actions, deps),
    )
    builder.add_node(
        AssistantNode.FINALIZE.value,
        _guarded(AssistantNode.FINALIZE, _finalize, deps),
    )

    builder.add_edge(START, AssistantNode.RECEIVE_REQUEST.value)
    for current, following in (
        (AssistantNode.RECEIVE_REQUEST, AssistantNode.RESOLVE_CONTEXT),
        (AssistantNode.RESOLVE_CONTEXT, AssistantNode.RETRIEVE_ALLOWED_FACTS),
        (AssistantNode.RETRIEVE_ALLOWED_FACTS, AssistantNode.DRAFT_RESPONSE),
        (AssistantNode.DRAFT_RESPONSE, AssistantNode.VALIDATE_POLICY),
    ):
        builder.add_conditional_edges(
            current.value,
            _route_after_read,
            {
                "continue": following.value,
                "finalize": AssistantNode.FINALIZE.value,
            },
        )
    builder.add_conditional_edges(
        AssistantNode.VALIDATE_POLICY.value,
        _route_after_read_or_wait,
        {
            "continue": AssistantNode.PROPOSE_ACTIONS.value,
            "finalize": AssistantNode.FINALIZE.value,
        },
    )
    builder.add_edge(AssistantNode.PROPOSE_ACTIONS.value, AssistantNode.FINALIZE.value)
    builder.add_edge(AssistantNode.FINALIZE.value, END)
    checkpointer = (
        deps.checkpointer
        if isinstance(deps.checkpointer, _SanitizedCheckpointer)
        else _SanitizedCheckpointer(deps.checkpointer)
    )
    return builder.compile(checkpointer=checkpointer)


def build_assistant_response(
    state: Mapping[str, object], *, run_id: uuid.UUID
) -> AssistantMessageResponse:
    """Proyección pública validada; el estado interno nunca se expone tal cual."""
    raw_status = state.get("status")
    try:
        status = AgentRunStatus(str(raw_status)) if raw_status else AgentRunStatus.PENDING
    except ValueError:
        status = AgentRunStatus.FAILED
    needs_review = bool(state.get("needs_review"))
    unsupported = state.get("unsupported_reason")
    if status in {AgentRunStatus.PENDING, AgentRunStatus.RUNNING}:
        public_status: Literal[
            "pending", "completed", "needs_review", "waiting_approval", "failed"
        ] = "pending"
    elif status is AgentRunStatus.WAITING_APPROVAL:
        public_status = "waiting_approval"
    elif status is AgentRunStatus.COMPLETED:
        public_status = (
            "needs_review" if needs_review or unsupported else "completed"
        )
    else:
        public_status = "failed"
    payload = {
        "run_id": run_id,
        "answer": str(state.get("answer") or _SAFE_ANSWER),
        "status": public_status,
        "citations": list(cast(list[object], state.get("citations") or [])),
        "proposed_actions": list(cast(list[object], state.get("proposed_actions") or [])),
        "limitations": list(cast(list[object], state.get("limitations") or [])),
        "unsupported_reason": None if unsupported is None else str(unsupported),
    }
    return AssistantMessageResponse.model_validate(payload)


__all__ = [
    "PROMPT_VERSION",
    "AssistantDependencies",
    "AssistantDraftOutput",
    "AssistantState",
    "build_assistant_response",
    "build_workspace_assistant_graph",
    "initial_assistant_state",
]
