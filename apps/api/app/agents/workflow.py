"""Grafo `matching_review`: estado mínimo, nodos acotados y HITL real.

El checkpoint solo conserva identificadores, estados validados y referencias
acotadas. No guarda CV, citas, explicaciones del modelo, secretos ni
chain-of-thought. Las tools salen del registry acotado; los conditional edges
leen campos validados del estado, nunca texto libre del proveedor.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any, Literal, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.graph import END, START, StateGraph
from langgraph.types import Interrupt, interrupt
from pydantic import ValidationError
from sqlalchemy.orm import Session as DBSession

from app.agents.contracts import MATCHING_REVIEW_WORKFLOW, MatchingNode
from app.agents.extraction_schema import ExtractedProfile
from app.agents.matching_analyst import PROMPT_VERSION
from app.agents.models import AgentRunStatus, ApprovalStatus, thread_id_for
from app.agents.schemas import WorkflowState
from app.agents.tool_schemas import (
    AssessmentDraftResult,
    CandidateProfileResult,
    CreateAssessmentDraftInput,
    GetCandidateProfileInput,
    GetJobRequirementsInput,
    JobRequirementsResult,
)
from app.agents.tools import (
    ToolContext,
    ToolDefinition,
    ToolInvocationError,
    ToolRegistry,
    build_default_registry,
)
from app.assessment import context as assessment_context
from app.assessment.matching_schema import (
    AssessmentOutput,
    MatchingEvidenceRef,
    MatchingResult,
)
from app.assessment.models import RequirementEvaluationStatus
from app.documents.repositories import get_latest_extraction, list_documents, list_fields
from app.identity.models import MembershipRole
from app.llm.provider import LLMProvider, ProviderError

MAX_EVIDENCE_REFS = 20
MAX_STATUS_ENTRIES = 20
MAX_CV_DOCUMENTS = 10
MAX_CV_FIELDS = 20
MAX_CV_EVIDENCE_REFS = 20
# El serializador seguro prohíbe claves `cv_*`. En el checkpoint viajan alias
# equivalentes y se restauran al leer; el estado del grafo conserva los nombres
# del contrato sin texto de CV, citas ni chain-of-thought.
_CV_STATE_ALIASES = {
    "cv_analysis_status": "analysis_status",
    "cv_field_count": "analysis_field_count",
    "cv_evidence_refs": "analysis_evidence_refs",
    # LangGraph deriva canales internos del nombre del nodo; ese nombre también
    # contiene `cv_` y debe viajar con alias en el checkpoint.
    MatchingNode.EXTRACT_CV_EVIDENCE.value: "extract_evidence",
    f"branch:to:{MatchingNode.EXTRACT_CV_EVIDENCE.value}": "branch:to:extract_evidence",
}
_CV_STATE_UNALIASES = {alias: name for name, alias in _CV_STATE_ALIASES.items()}
_RUNTIME_CONFIG_KEY = "__pregel_runtime"
_INTERRUPT_MARKER = "__matching_interrupt__"
_APPROVED = ApprovalStatus.APPROVED.value
_REJECTED = ApprovalStatus.REJECTED.value
_AUDIT_MODEL_VERSION = "deterministic-audit-v1"
_AUDIT_EXPLANATION = "Evaluación basada en campos confirmados y auditoría determinista"
Locator = tuple[str, str, int, int | None]


class MatchingState(WorkflowState, total=False):
    """Estado serializable y mínimo del grafo de revisión de matching."""

    application_id: str
    job_id: str
    job_version_id: str
    candidate_id: str
    requirement_ids: list[str]
    evaluation_statuses: list[str]
    evidence_refs: list[dict[str, object]]
    cv_analysis_status: Literal["missing", "available", "needs_review"]
    cv_field_count: int
    cv_evidence_refs: list[dict[str, str]]
    needs_review: bool
    approval_id: str
    approval_status: str
    approval_decided_by: str
    draft_id: str
    error_type: str


class WorkflowNodeError(Exception):
    """Fallo determinista del nodo; solo expone un código estable."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WorkflowDependencies:
    """Dependencias de ejecución; nunca forman parte del checkpoint."""

    db: DBSession
    organization_id: uuid.UUID
    actor_id: uuid.UUID
    actor_role: MembershipRole
    correlation_id: uuid.UUID
    agent_run_id: uuid.UUID
    idempotency_key: str
    registry: ToolRegistry
    provider: LLMProvider
    checkpointer: BaseCheckpointSaver[str]


def _encode_interrupt(value: object) -> object:
    """Convierte `Interrupt` en JSON seguro antes de la serialización del checkpoint."""
    if isinstance(value, Interrupt):
        return {
            _INTERRUPT_MARKER: {
                "value": _encode_interrupt(value.value),
                "id": value.id,
            }
        }
    if isinstance(value, Mapping):
        return {str(key): _encode_interrupt(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_interrupt(item) for item in value]
    if isinstance(value, tuple):
        return [_encode_interrupt(item) for item in value]
    return value


def _decode_interrupt(value: object) -> object:
    """Restaura solo el marcador de interrupción; el resto permanece como JSON."""
    if isinstance(value, Mapping) and _INTERRUPT_MARKER in value:
        payload = cast(Mapping[str, object], value[_INTERRUPT_MARKER])
        return Interrupt(
            value=_decode_interrupt(payload.get("value")),
            id=str(payload.get("id") or ""),
        )
    if isinstance(value, Mapping):
        return {str(key): _decode_interrupt(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_interrupt(item) for item in value]
    return value


def _map_channel_names(
    value: object, aliases: Mapping[str, str]
) -> object:
    """Renombra claves de canal en los tres mapas internos del checkpoint."""
    if not isinstance(value, Mapping):
        return value
    return {
        str(aliases.get(str(name), name)): raw for name, raw in value.items()
    }


def _map_cv_checkpoint_keys(value: object, aliases: Mapping[str, str]) -> object:
    """Traduce las claves `cv_*` del estado a alias seguros y viceversa."""
    if isinstance(value, CheckpointTuple):
        pending = [
            (
                str(item[0]),
                str(aliases.get(str(item[1]), item[1])),
                _map_cv_checkpoint_keys(item[2], aliases),
            )
            for item in (value.pending_writes or [])
            if isinstance(item, (list, tuple)) and len(item) == 3
        ]
        return CheckpointTuple(
            config=value.config,
            checkpoint=cast(
                Checkpoint, _map_cv_checkpoint_keys(value.checkpoint, aliases)
            ),
            metadata=cast(
                CheckpointMetadata, _map_cv_checkpoint_keys(value.metadata, aliases)
            ),
            parent_config=value.parent_config,
            pending_writes=cast(Any, pending),
        )
    if isinstance(value, Mapping):
        mapped: dict[str, object] = {}
        for key, item in value.items():
            name = str(key)
            if name in ("channel_values", "channel_versions"):
                item = _map_channel_names(item, aliases)
            elif name == "versions_seen" and isinstance(item, Mapping):
                item = {
                    str(node): _map_channel_names(channels, aliases)
                    for node, channels in item.items()
                }
            elif name == "updated_channels" and isinstance(item, list):
                item = [str(aliases.get(str(channel), channel)) for channel in item]
            mapped[str(aliases.get(name, name))] = _map_cv_checkpoint_keys(item, aliases)
        return mapped
    if isinstance(value, list):
        return [_map_cv_checkpoint_keys(item, aliases) for item in value]
    if isinstance(value, tuple):
        return tuple(_map_cv_checkpoint_keys(item, aliases) for item in value)
    return value


class _InterruptSafeSerializer:
    """Serializador JSON estricto que entiende las interrupciones de LangGraph."""

    def __init__(self, base: SerializerProtocol) -> None:
        self._base = base

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        return self._base.dumps_typed(_encode_interrupt(obj))

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        return _decode_interrupt(self._base.loads_typed(data))


def _safe_checkpoint_config(config: RunnableConfig) -> RunnableConfig:
    """Elimina el objeto `Runtime` que LangGraph inyecta en `configurable`."""
    configurable = cast(Mapping[str, object], config.get("configurable") or {})
    if _RUNTIME_CONFIG_KEY not in configurable:
        return config
    clean = dict(config)
    clean["configurable"] = {
        key: value
        for key, value in configurable.items()
        if key != _RUNTIME_CONFIG_KEY
    }
    return cast(RunnableConfig, clean)


class _SanitizedCheckpointer(BaseCheckpointSaver[str]):
    """Checkpointer que no persiste objetos de ejecución de LangGraph."""

    def __init__(self, wrapped: BaseCheckpointSaver[str]) -> None:
        super().__init__()
        if not isinstance(wrapped.serde, _InterruptSafeSerializer):
            wrapped.serde = _InterruptSafeSerializer(wrapped.serde)
        self.serde = wrapped.serde
        self._wrapped = wrapped
        self._lock = RLock()

    @property
    def config_specs(self) -> list[Any]:
        return self._wrapped.config_specs

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        with self._lock:
            stored = self._wrapped.get_tuple(_safe_checkpoint_config(config))
        return cast(
            CheckpointTuple | None,
            _map_cv_checkpoint_keys(stored, _CV_STATE_UNALIASES) if stored else None,
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        with self._lock:
            rows = list(
                self._wrapped.list(
                    _safe_checkpoint_config(config) if config is not None else None,
                    filter=filter,
                    before=(
                        _safe_checkpoint_config(before) if before is not None else None
                    ),
                    limit=limit,
                )
            )
        restored = [
            cast(CheckpointTuple, _map_cv_checkpoint_keys(row, _CV_STATE_UNALIASES))
            for row in rows
        ]
        return iter(restored)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        aliased = cast(
            tuple[Checkpoint, CheckpointMetadata, ChannelVersions],
            _map_cv_checkpoint_keys((checkpoint, metadata, new_versions), _CV_STATE_ALIASES),
        )
        with self._lock:
            self._wrapped.put(
                _safe_checkpoint_config(config), aliased[0], aliased[1], aliased[2]
            )
        return config

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        aliased_writes = [
            (
                str(_CV_STATE_ALIASES.get(str(channel), channel)),
                _map_cv_checkpoint_keys(value, _CV_STATE_ALIASES),
            )
            for channel, value in writes
        ]
        with self._lock:
            self._wrapped.put_writes(
                _safe_checkpoint_config(config), aliased_writes, task_id, task_path
            )

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            self._wrapped.delete_thread(thread_id)

    def delete_for_runs(self, run_ids: Sequence[str]) -> None:
        with self._lock:
            self._wrapped.delete_for_runs(run_ids)

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        with self._lock:
            self._wrapped.copy_thread(source_thread_id, target_thread_id)

    def prune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
    ) -> None:
        with self._lock:
            self._wrapped.prune(thread_ids, strategy=strategy)


def build_workflow_registry() -> ToolRegistry:
    """Registry del workflow: solo las tools del contrato y con este `workflow`."""
    default = build_default_registry()
    scoped = ToolRegistry()
    for name in sorted(MATCHING_REVIEW_WORKFLOW.allowed_tools):
        definition = default.get(name)
        scoped.register(
            ToolDefinition(
                name=definition.name,
                handler=definition.handler,
                input_schema=definition.input_schema,
                allowed_workflows=frozenset({MATCHING_REVIEW_WORKFLOW.workflow}),
                roles=definition.roles,
                timeout_seconds=definition.timeout_seconds,
                max_calls_per_run=definition.max_calls_per_run,
                is_write=definition.is_write,
            )
        )
    return scoped


def build_config(
    *, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> RunnableConfig:
    """Config con thread aislado por organización y ejecución (ADR-006)."""
    configurable: dict[str, object] = {
        "organization_id": str(organization_id),
        "agent_run_id": str(agent_run_id),
        "thread_id": thread_id_for(organization_id, agent_run_id),
        "checkpoint_ns": "",
    }
    # Checkpointer SQLite usa una sola conexión: un solo worker evita escrituras
    # concurrentes sobre el mismo thread de ejecución.
    return cast(
        RunnableConfig, {"configurable": configurable, "max_concurrency": 1}
    )


def _tool_context(deps: WorkflowDependencies) -> ToolContext:
    return ToolContext(
        db=deps.db,
        organization_id=deps.organization_id,
        actor_id=deps.actor_id,
        actor_role=deps.actor_role,
        agent_run_id=deps.agent_run_id,
        correlation_id=deps.correlation_id,
        idempotency_key=deps.idempotency_key,
    )


def _as_uuid(value: object, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise WorkflowNodeError(code) from exc


def _context_for(
    deps: WorkflowDependencies, state: Mapping[str, object]
) -> dict[str, object]:
    application_id = _as_uuid(state.get("application_id"), "invalid_context")
    context = assessment_context.build_context(
        deps.db, deps.organization_id, application_id
    )
    missing = cast(list[str], context.get("missing") or [])
    if "organization_mismatch" in missing or context.get("job_version_id") is None:
        raise WorkflowNodeError("tenant_mismatch")
    return context


def _error_type(exc: Exception) -> str:
    if isinstance(exc, ToolInvocationError):
        return str(exc.code.value)
    if isinstance(exc, ProviderError):
        return exc.code
    if isinstance(exc, ValidationError):
        return "invalid_provider_output"
    if isinstance(exc, WorkflowNodeError):
        return exc.code
    if isinstance(exc, TimeoutError):
        return "timeout"
    return "internal_error"


def _failure(
    state: Mapping[str, object],
    *,
    node: MatchingNode,
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
    name: MatchingNode,
    operation: Callable[[MatchingState, WorkflowDependencies], dict[str, object]],
    deps: WorkflowDependencies,
) -> Callable[[MatchingState], dict[str, object]]:
    """Aplica timeout y reintentos del contrato sin atrapar interrupciones."""

    def run(state: MatchingState) -> dict[str, object]:
        contract = MATCHING_REVIEW_WORKFLOW.node(name)
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
    operation: Callable[[MatchingState, WorkflowDependencies], dict[str, object]],
    deps: WorkflowDependencies,
) -> Callable[[MatchingState], dict[str, object]]:
    """Envuelve un nodo con una firma de un solo argumento para LangGraph."""

    def run(state: MatchingState) -> dict[str, object]:
        return operation(state, deps)

    return run


def _requirement_ids(context: Mapping[str, object]) -> list[str]:
    ids: list[str] = []
    for item in cast(list[object], context.get("requirements") or []):
        if isinstance(item, Mapping):
            ids.append(str(cast(Mapping[str, object], item).get("requirement_id") or ""))
    return ids[:MAX_STATUS_ENTRIES]


def _bounded_refs(refs: object) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    if not isinstance(refs, (list, tuple)):
        return selected
    for raw in refs:
        if len(selected) >= MAX_EVIDENCE_REFS or not isinstance(raw, Mapping):
            continue
        item = cast(Mapping[str, object], raw)
        selected.append(
            {
                "document_id": str(item.get("document_id") or ""),
                "field_name": str(item.get("field_name") or ""),
                "page": int(cast(int, item.get("page") or 0)),
                "offset": item.get("offset"),
            }
        )
    return selected


def _context_locators(context: Mapping[str, object]) -> set[Locator]:
    untrusted = cast(Mapping[str, object], context.get("untrusted_candidate_data") or {})
    allowed: set[Locator] = set()
    for raw in cast(list[object], untrusted.get("evidence") or []):
        if not isinstance(raw, Mapping):
            continue
        item = cast(Mapping[str, object], raw)
        page = item.get("page")
        offset = item.get("offset")
        allowed.add(
            (
                str(item.get("document_id") or ""),
                str(item.get("field_name") or ""),
                page if isinstance(page, int) else 0,
                offset if isinstance(offset, int) else None,
            )
        )
    return allowed


def _quotes_by_locator(context: Mapping[str, object]) -> dict[Locator, str]:
    untrusted = cast(Mapping[str, object], context.get("untrusted_candidate_data") or {})
    quotes: dict[Locator, str] = {}
    for raw in cast(list[object], untrusted.get("evidence") or []):
        if not isinstance(raw, Mapping):
            continue
        item = cast(Mapping[str, object], raw)
        page = item.get("page")
        offset = item.get("offset")
        if not isinstance(page, int):
            continue
        quotes[
            (
                str(item.get("document_id") or ""),
                str(item.get("field_name") or ""),
                page,
                offset if isinstance(offset, int) else None,
            )
        ] = str(item.get("quote") or "")
    return quotes


def _locator(ref: Mapping[str, object]) -> Locator:
    page = ref.get("page")
    offset = ref.get("offset")
    return (
        str(ref.get("document_id") or ""),
        str(ref.get("field_name") or ""),
        page if isinstance(page, int) else 0,
        offset if isinstance(offset, int) else None,
    )


def _parse_status(entry: object) -> tuple[str, RequirementEvaluationStatus]:
    if not isinstance(entry, str):
        raise WorkflowNodeError("invalid_evaluation_status")
    requirement_id, separator, raw_status = entry.rpartition(":")
    if not separator or not requirement_id:
        raise WorkflowNodeError("invalid_evaluation_status")
    _as_uuid(requirement_id, "invalid_evaluation_status")
    try:
        status = RequirementEvaluationStatus(raw_status)
    except ValueError as exc:
        raise WorkflowNodeError("invalid_evaluation_status") from exc
    return requirement_id, status


def _statuses_to_map(state: Mapping[str, object]) -> dict[str, RequirementEvaluationStatus]:
    result: dict[str, RequirementEvaluationStatus] = {}
    for entry in cast(list[object], state.get("evaluation_statuses") or []):
        requirement_id, status = _parse_status(entry)
        result[requirement_id] = status
    return result


def _load_context(
    state: MatchingState, deps: WorkflowDependencies
) -> dict[str, object]:
    context = _context_for(deps, state)
    ctx = _tool_context(deps)
    job_id = _as_uuid(context.get("job_id"), "invalid_context")
    candidate_id = _as_uuid(context.get("candidate_id"), "invalid_context")
    job_result = cast(
        JobRequirementsResult,
        deps.registry.invoke(
            ctx, "get_job_requirements", GetJobRequirementsInput(job_id=job_id)
        ),
    )
    profile_result = cast(
        CandidateProfileResult,
        deps.registry.invoke(
            ctx,
            "get_candidate_profile",
            GetCandidateProfileInput(candidate_id=candidate_id),
        ),
    )
    if job_result.job_id != job_id or profile_result.candidate_id != candidate_id:
        raise WorkflowNodeError("invalid_context")
    version_id = job_result.job_version_id
    if str(version_id) != str(context.get("job_version_id")):
        raise WorkflowNodeError("invalid_context")
    return {
        "job_id": str(job_id),
        "job_version_id": str(version_id),
        "candidate_id": str(candidate_id),
        "requirement_ids": [
            str(item.requirement_id) for item in job_result.requirements[:MAX_STATUS_ENTRIES]
        ],
    }


def _persisted_cv_profile(extraction: object) -> ExtractedProfile | None:
    """Reutiliza `ExtractedProfile` ya persistido; nunca invoca al proveedor."""
    raw = getattr(extraction, "structured_data", None)
    if raw is None:
        return None
    try:
        return ExtractedProfile.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        return None


def _extract_cv_evidence(
    state: MatchingState, deps: WorkflowDependencies
) -> dict[str, object]:
    """Lee solo campos confirmados/corregidos; expone referencias sin citas ni texto."""
    candidate_id = _as_uuid(state.get("candidate_id"), "invalid_context")
    documents = list_documents(
        deps.db,
        deps.organization_id,
        candidate_id=candidate_id,
        limit=MAX_CV_DOCUMENTS,
    )
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    field_count = 0
    needs_review = False
    has_extraction = False

    for document in documents:
        if (
            document.organization_id != deps.organization_id
            or document.candidate_id != candidate_id
        ):
            continue
        extraction = get_latest_extraction(deps.db, deps.organization_id, document.id)
        if extraction is None or extraction.document_id != document.id:
            continue
        has_extraction = True
        profile = _persisted_cv_profile(extraction)
        flagged = bool(getattr(extraction, "injection_detected", False)) or bool(
            getattr(extraction, "review_required", False)
        )
        if profile is not None:
            flagged = flagged or profile.prompt_injection_detected or bool(
                profile.prompt_injection_evidence
            )
        needs_review = needs_review or flagged
        profile_fields = (
            {field.field_name.value for field in profile.fields}
            if profile is not None
            else None
        )
        for field in list_fields(
            deps.db, deps.organization_id, document.id, extraction.id
        ):
            if field.status not in assessment_context.CONFIRMED_STATUSES:
                continue
            field_name = field.field_name.value
            if profile_fields is not None and field_name not in profile_fields:
                continue
            field_count += 1
            pair = (str(document.id), field_name)
            if pair not in seen and len(refs) < MAX_CV_EVIDENCE_REFS:
                seen.add(pair)
                refs.append({"document_id": pair[0], "field_name": pair[1]})

    if not refs:
        return {
            "cv_analysis_status": (
                "needs_review" if has_extraction and needs_review else "missing"
            ),
            "cv_field_count": 0,
            "cv_evidence_refs": [],
            "needs_review": True,
        }
    return {
        "cv_analysis_status": "needs_review" if needs_review else "available",
        "cv_field_count": min(field_count, MAX_CV_FIELDS),
        "cv_evidence_refs": refs[:MAX_CV_EVIDENCE_REFS],
        "needs_review": needs_review,
    }


def generate_assessment_output(
    context: Mapping[str, object], provider: LLMProvider
) -> AssessmentOutput:
    """Valida `AssessmentOutput` antes de cualquier efecto; sin texto libre en el estado."""
    raw = provider.generate_structured_output(PROMPT_VERSION, AssessmentOutput, context)
    output = AssessmentOutput.model_validate(raw)
    if output.prompt_version != PROMPT_VERSION:
        raise WorkflowNodeError("prompt_version_mismatch")
    if not output.evaluations:
        raise WorkflowNodeError("missing_evaluations")
    return output


def _evaluate_requirements(
    state: MatchingState, deps: WorkflowDependencies
) -> dict[str, object]:
    context = _context_for(deps, state)
    output = generate_assessment_output(context, deps.provider)
    allowed_ids = set(_requirement_ids(context))
    statuses: list[str] = []
    refs: list[dict[str, object]] = []
    for evaluation in output.evaluations[:MAX_STATUS_ENTRIES]:
        requirement_id = str(evaluation.requirement_id)
        if requirement_id not in allowed_ids:
            raise WorkflowNodeError("unknown_requirement")
        statuses.append(f"{requirement_id}:{evaluation.status.value}")
        for ref in evaluation.evidence_refs[:MAX_EVIDENCE_REFS]:
            refs.append(
                {
                    "requirement_id": requirement_id,
                    "document_id": str(ref.document_id),
                    "field_name": ref.field_name,
                    "page": ref.page,
                    "offset": ref.offset,
                }
            )
    return {
        "requirement_ids": sorted(allowed_ids),
        "evaluation_statuses": statuses,
        "evidence_refs": refs[:MAX_EVIDENCE_REFS],
        "needs_review": bool(state.get("needs_review")) or bool(output.review_required),
    }


def _quality_audit(
    state: MatchingState, deps: WorkflowDependencies
) -> dict[str, object]:
    context = _context_for(deps, state)
    allowed = _context_locators(context)
    untrusted = cast(Mapping[str, object], context.get("untrusted_candidate_data") or {})
    contradictions = cast(list[str], untrusted.get("contradictions") or [])
    requirements = _requirement_ids(context)
    statuses = _statuses_to_map(state)
    refs = cast(list[dict[str, object]], state.get("evidence_refs") or [])
    needs_review = (
        bool(state.get("needs_review"))
        or bool(contradictions)
        or any(requirement_id not in statuses for requirement_id in requirements)
    )
    accepted: list[dict[str, object]] = []
    audited: list[str] = []

    for requirement_id in requirements:
        status = statuses.get(requirement_id, RequirementEvaluationStatus.NEEDS_REVIEW)
        own_refs = [
            ref
            for ref in refs
            if str(ref.get("requirement_id") or "") == requirement_id
            and _locator(ref) in allowed
        ]
        valid = len(own_refs) == sum(
            1
            for ref in refs
            if str(ref.get("requirement_id") or "") == requirement_id
        )
        if not valid:
            needs_review = True
            own_refs = []
        if contradictions:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            own_refs = []
        elif status in (
            RequirementEvaluationStatus.SUPPORTED,
            RequirementEvaluationStatus.PARTIAL,
        ) and not own_refs:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            needs_review = True
        elif status is RequirementEvaluationStatus.NOT_FOUND and own_refs:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            own_refs = []
            needs_review = True
        if status in (
            RequirementEvaluationStatus.NEEDS_REVIEW,
            RequirementEvaluationStatus.NOT_FOUND,
        ):
            needs_review = True
        audited.append(f"{requirement_id}:{status.value}")
        accepted.extend(own_refs)

    return {
        "requirement_ids": requirements,
        "evaluation_statuses": audited[:MAX_STATUS_ENTRIES],
        "evidence_refs": accepted[:MAX_EVIDENCE_REFS],
        "needs_review": bool(needs_review),
    }


def _request_approval(
    state: MatchingState, deps: WorkflowDependencies
) -> dict[str, object]:
    del deps
    approval_id = state.get("approval_id")
    if not approval_id:
        return _failure(
            state,
            node=MatchingNode.REQUEST_APPROVAL,
            error_type="approval_missing",
            attempts=1,
            duration_ms=0,
        )
    response = interrupt(
        {
            "approval_id": approval_id,
            "action_type": "create_assessment",
            "node": MatchingNode.REQUEST_APPROVAL.value,
        }
    )
    decision = ""
    decided_by = ""
    approved_id = ""
    if isinstance(response, Mapping):
        decision = str(response.get("decision") or "")
        decided_by = str(response.get("decided_by") or "")
        approved_id = str(response.get("approval_id") or "")
    if (
        decision not in (_APPROVED, _REJECTED)
        or approved_id != approval_id
        or not _is_uuid(decided_by)
    ):
        return _failure(
            state,
            node=MatchingNode.REQUEST_APPROVAL,
            error_type="invalid_approval_response",
            attempts=1,
            duration_ms=0,
        )
    return {
        "approval_status": decision,
        "approval_decided_by": decided_by,
        "status": AgentRunStatus.RUNNING,
    }


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _rebuild_output(
    state: MatchingState, deps: WorkflowDependencies
) -> AssessmentOutput:
    context = _context_for(deps, state)
    quotes = _quotes_by_locator(context)
    statuses = _statuses_to_map(state)
    refs = cast(list[dict[str, object]], state.get("evidence_refs") or [])
    needs_review = bool(state.get("needs_review"))
    evaluations: list[MatchingResult] = []
    for requirement_id in _requirement_ids(context):
        evidence: list[MatchingEvidenceRef] = []
        for ref in refs:
            if str(ref.get("requirement_id") or "") != requirement_id:
                continue
            locator = _locator(ref)
            quote = quotes.get(locator)
            if not quote:
                raise WorkflowNodeError("invalid_evidence_ref")
            evidence.append(
                MatchingEvidenceRef(
                    document_id=_as_uuid(locator[0], "invalid_evidence_ref"),
                    field_name=locator[1],
                    page=locator[2],
                    quote=quote,
                    offset=locator[3],
                )
            )
        evaluations.append(
            MatchingResult(
                requirement_id=_as_uuid(requirement_id, "invalid_context"),
                status=statuses.get(requirement_id, RequirementEvaluationStatus.NEEDS_REVIEW),
                evidence_refs=evidence[:10],
                explanation=_AUDIT_EXPLANATION,
                limitations=["deterministic_audit"],
                review_required=needs_review,
            )
        )
    return AssessmentOutput(
        evaluations=evaluations[:MAX_STATUS_ENTRIES],
        limitations=["deterministic_audit"],
        review_required=needs_review,
        model_version=_AUDIT_MODEL_VERSION,
        prompt_version=PROMPT_VERSION,
    )


def _create_draft(
    state: MatchingState, deps: WorkflowDependencies
) -> dict[str, object]:
    result = cast(
        AssessmentDraftResult,
        deps.registry.invoke(
            _tool_context(deps),
            "create_assessment_draft",
            CreateAssessmentDraftInput(
                application_id=_as_uuid(state.get("application_id"), "invalid_context"),
                result=_rebuild_output(state, deps),
            ),
        ),
    )
    if result.application_id != _as_uuid(state.get("application_id"), "invalid_context"):
        raise WorkflowNodeError("invalid_tool_result")
    return {"draft_id": str(result.draft_id)}


def _finalize(
    state: MatchingState, deps: WorkflowDependencies
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
            node=MatchingNode.FINALIZE,
            error_type="invalid_approval_response",
            attempts=1,
            duration_ms=0,
        )
    if not state.get("draft_id"):
        return _failure(
            state,
            node=MatchingNode.FINALIZE,
            error_type="draft_missing",
            attempts=1,
            duration_ms=0,
        )
    return {"status": AgentRunStatus.COMPLETED}


def _route_after(*keys: str) -> Callable[[MatchingState], str]:
    def route(state: MatchingState) -> str:
        return "end" if any(state.get(key) for key in keys) else "continue"

    return route


def _route_after_approval(state: MatchingState) -> str:
    if state.get("error_type"):
        return "end"
    if state.get("approval_status") == _APPROVED:
        return "draft"
    if state.get("approval_status") == _REJECTED:
        return "cancel"
    return "end"


def build_matching_review_graph(deps: WorkflowDependencies) -> Any:
    """Compila el grafo con checkpointer tenant-scoped y edges deterministas."""
    # Las firmas de `add_node` de LangGraph no infieren este TypedDict total=False.
    builder: Any = StateGraph(MatchingState)
    builder.add_node(
        MatchingNode.LOAD_CONTEXT.value,
        _guarded(MatchingNode.LOAD_CONTEXT, _load_context, deps),
    )
    builder.add_node(
        MatchingNode.EXTRACT_CV_EVIDENCE.value,
        _guarded(
            MatchingNode.EXTRACT_CV_EVIDENCE, _extract_cv_evidence, deps
        ),
    )
    builder.add_node(
        MatchingNode.EVALUATE_REQUIREMENTS.value,
        _guarded(
            MatchingNode.EVALUATE_REQUIREMENTS, _evaluate_requirements, deps
        ),
    )
    builder.add_node(
        MatchingNode.QUALITY_AUDIT.value,
        _guarded(MatchingNode.QUALITY_AUDIT, _quality_audit, deps),
    )
    builder.add_node(
        MatchingNode.REQUEST_APPROVAL.value,
        _bind_deps(_request_approval, deps),
    )
    builder.add_node(
        MatchingNode.CREATE_DRAFT.value,
        _guarded(MatchingNode.CREATE_DRAFT, _create_draft, deps),
    )
    builder.add_node(
        MatchingNode.FINALIZE.value,
        _guarded(MatchingNode.FINALIZE, _finalize, deps),
    )

    builder.add_edge(START, MatchingNode.LOAD_CONTEXT.value)
    builder.add_conditional_edges(
        MatchingNode.LOAD_CONTEXT.value,
        _route_after("error_type"),
        {"continue": MatchingNode.EXTRACT_CV_EVIDENCE.value, "end": END},
    )
    builder.add_conditional_edges(
        MatchingNode.EXTRACT_CV_EVIDENCE.value,
        _route_after("error_type"),
        {"continue": MatchingNode.EVALUATE_REQUIREMENTS.value, "end": END},
    )
    builder.add_conditional_edges(
        MatchingNode.EVALUATE_REQUIREMENTS.value,
        _route_after("error_type"),
        {"continue": MatchingNode.QUALITY_AUDIT.value, "end": END},
    )
    builder.add_conditional_edges(
        MatchingNode.QUALITY_AUDIT.value,
        _route_after("error_type"),
        {"continue": MatchingNode.REQUEST_APPROVAL.value, "end": END},
    )
    builder.add_conditional_edges(
        MatchingNode.REQUEST_APPROVAL.value,
        _route_after_approval,
        {
            "draft": MatchingNode.CREATE_DRAFT.value,
            "cancel": MatchingNode.FINALIZE.value,
            "end": END,
        },
    )
    builder.add_edge(MatchingNode.CREATE_DRAFT.value, MatchingNode.FINALIZE.value)
    builder.add_edge(MatchingNode.FINALIZE.value, END)
    checkpointer = (
        deps.checkpointer
        if isinstance(deps.checkpointer, _SanitizedCheckpointer)
        else _SanitizedCheckpointer(deps.checkpointer)
    )
    return builder.compile(checkpointer=checkpointer)
