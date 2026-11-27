"""Contratos explícitos de los workflows reales del runtime.

No hay registro genérico de agentes: este módulo describe exactamente los grafos
implementados en `app.agents.workflow`, `app.agents.orchestrator` y el contrato
`workspace_assistant` de la Fase 17 (SDD 9.3, ADR-006, ADR-020). Las tools
listadas son subset del registry de `app.agents.tools`; ningún documento puede
ampliar esta lista ni los permisos por nodo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.models import AgentRunStatus


class MatchingNode(StrEnum):
    """Nodos ordenados del grafo; el orden es parte del contrato versionado."""

    LOAD_CONTEXT = "load_context"
    EXTRACT_CV_EVIDENCE = "extract_cv_evidence"
    EVALUATE_REQUIREMENTS = "evaluate_requirements"
    QUALITY_AUDIT = "quality_audit"
    REQUEST_APPROVAL = "request_approval"
    CREATE_DRAFT = "create_draft"
    FINALIZE = "finalize"


class MatchingTool(StrEnum):
    """Subconjunto del registry autorizado para `matching_review`."""

    GET_JOB_REQUIREMENTS = "get_job_requirements"
    GET_CANDIDATE_PROFILE = "get_candidate_profile"
    GET_CONFIRMED_DOCUMENT_TEXT = "get_confirmed_document_text"
    CREATE_ASSESSMENT_DRAFT = "create_assessment_draft"


class OrchestrationNode(StrEnum):
    """Nodos ordenados del orquestador; el orden es parte del contrato."""

    RECEIVE_TASK = "receive_task"
    SELECT_FLOW = "select_flow"
    DELEGATE = "delegate"
    REQUEST_APPROVAL = "request_approval"
    FINALIZE = "finalize"


class AssistantNode(StrEnum):
    """Nodos ordenados del asistente; el orden es parte del contrato (ADR-020)."""

    RECEIVE_REQUEST = "receive_request"
    RESOLVE_CONTEXT = "resolve_context"
    RETRIEVE_ALLOWED_FACTS = "retrieve_allowed_facts"
    DRAFT_RESPONSE = "draft_response"
    VALIDATE_POLICY = "validate_policy"
    PROPOSE_ACTIONS = "propose_actions"
    FINALIZE = "finalize"


class AssistantTool(StrEnum):
    """Subconjunto del registry autorizado para `workspace_assistant`."""

    GET_JOB_REQUIREMENTS = "get_job_requirements"
    GET_CANDIDATE_PROFILE = "get_candidate_profile"
    GET_CONFIRMED_DOCUMENT_TEXT = "get_confirmed_document_text"
    GET_AUTOMATION_STATUS = "get_automation_status"
    GET_WORKSPACE_SUMMARY = "get_workspace_summary"
    LIST_JOBS = "list_jobs"
    LIST_CANDIDATES = "list_candidates"
    LIST_APPLICATIONS = "list_applications"
    GET_FORM_SCHEMA = "get_form_schema"
    GET_PLATFORM_CAPABILITIES = "get_platform_capabilities"
    CREATE_ASSESSMENT_DRAFT = "create_assessment_draft"
    CREATE_INTERVIEW_QUESTIONS = "create_interview_questions"
    CREATE_MESSAGE_DRAFT = "create_message_draft"
    REQUEST_HUMAN_APPROVAL = "request_human_approval"


class AssistantSurface(StrEnum):
    """Pantallas donde el asistente puede recibir contexto."""

    DASHBOARD = "dashboard"
    JOBS = "jobs"
    CANDIDATES = "candidates"
    APPLICATIONS = "applications"
    ASSESSMENT = "assessment"
    INTERVIEWS = "interviews"
    DOCUMENTS = "documents"
    AUTOMATIONS = "automations"
    INTEGRATIONS = "integrations"
    ANALYTICS = "analytics"
    AGENTS = "agents"


class AssistantActionType(StrEnum):
    """Acciones tipadas; fuera de esta lista la salida se rechaza."""

    EXPLAIN = "explain"
    FILL_FORM = "fill_form"
    NAVIGATE = "navigate"
    CREATE_DRAFT = "create_draft"
    REQUEST_APPROVAL = "request_approval"


class AssistantFormId(StrEnum):
    """Formularios permitidos; el LLM no puede inventar otros."""

    JOB_CREATE = "job.create"
    CANDIDATE_CREATE = "candidate.create"
    ASSESSMENT_CRITERION = "assessment.criterion"
    INTERVIEW_GUIDE = "interview.guide"
    AUTOMATION_RULE = "automation.rule"
    MESSAGE_DRAFT = "message.draft"


class FieldOrigin(StrEnum):
    """Origen de cada campo de un patch propuesto."""

    USER_REQUEST = "user_request"
    TOOL_FACT = "tool_fact"
    NEEDS_USER_INPUT = "needs_user_input"


WorkflowNodeName = MatchingNode | OrchestrationNode | AssistantNode


@dataclass(frozen=True)
class NodeContract:
    """Límite ejecutable por nodo: timeout y reintentos acotados."""

    name: WorkflowNodeName
    timeout_seconds: float
    max_retries: int = 1


@dataclass(frozen=True)
class WorkflowContract:
    """Contrato inmutable de un solo workflow; sin extensiones dinámicas."""

    workflow: str
    version: str
    nodes: tuple[NodeContract, ...]
    allowed_tools: frozenset[str]
    max_retries: int
    approval_action_type: str
    interrupt_before_effects: WorkflowNodeName
    terminal_statuses: frozenset[AgentRunStatus]

    def node(self, name: WorkflowNodeName) -> NodeContract:
        """Devuelve el contrato del nodo; falla si el nombre no pertenece al grafo."""
        for contract in self.nodes:
            if contract.name is name:
                return contract
        raise KeyError(name)


MATCHING_REVIEW_WORKFLOW = WorkflowContract(
    workflow="matching_review",
    version="1.1.0",
    nodes=(
        NodeContract(MatchingNode.LOAD_CONTEXT, timeout_seconds=2.0),
        NodeContract(MatchingNode.EXTRACT_CV_EVIDENCE, timeout_seconds=2.0, max_retries=1),
        NodeContract(MatchingNode.EVALUATE_REQUIREMENTS, timeout_seconds=5.0),
        NodeContract(MatchingNode.QUALITY_AUDIT, timeout_seconds=2.0),
        NodeContract(MatchingNode.REQUEST_APPROVAL, timeout_seconds=2.0),
        NodeContract(MatchingNode.CREATE_DRAFT, timeout_seconds=2.0),
        NodeContract(MatchingNode.FINALIZE, timeout_seconds=2.0),
    ),
    allowed_tools=frozenset(tool.value for tool in MatchingTool),
    max_retries=1,
    approval_action_type="create_assessment",
    interrupt_before_effects=MatchingNode.REQUEST_APPROVAL,
    terminal_statuses=frozenset(
        {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
)


RECRUITMENT_ORCHESTRATION_WORKFLOW = WorkflowContract(
    workflow="recruitment_orchestration",
    version="1.0.0",
    nodes=(
        NodeContract(OrchestrationNode.RECEIVE_TASK, timeout_seconds=2.0),
        NodeContract(OrchestrationNode.SELECT_FLOW, timeout_seconds=2.0),
        NodeContract(OrchestrationNode.DELEGATE, timeout_seconds=2.0),
        NodeContract(OrchestrationNode.REQUEST_APPROVAL, timeout_seconds=2.0),
        NodeContract(OrchestrationNode.FINALIZE, timeout_seconds=2.0),
    ),
    allowed_tools=frozenset(
        {
            MatchingTool.GET_JOB_REQUIREMENTS.value,
            MatchingTool.GET_CANDIDATE_PROFILE.value,
            MatchingTool.GET_CONFIRMED_DOCUMENT_TEXT.value,
        }
    ),
    max_retries=1,
    approval_action_type="delegate_specialized_flow",
    interrupt_before_effects=OrchestrationNode.REQUEST_APPROVAL,
    terminal_statuses=frozenset(
        {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
)


class _AssistantInput(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AssistantMessageSnapshot(_AssistantInput):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AssistantMessageRequest(_AssistantInput):
    """Mensaje entrante; el tenant y el rol vienen del contexto autenticado."""

    schema_version: Literal["1.0"] = "1.0"
    message: str = Field(min_length=1, max_length=2000)
    surface: AssistantSurface
    resource_ref: uuid.UUID | None = None
    recent_messages: list[AssistantMessageSnapshot] = Field(default_factory=list, max_length=8)
    idempotency_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _limit_history_size(self) -> AssistantMessageRequest:
        if sum(len(item.content) for item in self.recent_messages) > 4000:
            raise ValueError("Historial reciente demasiado largo")
        return self


class EvidenceRef(_AssistantInput):
    quote: str = Field(min_length=1, max_length=300)
    organization_id: uuid.UUID
    document_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    page: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def _require_source(self) -> EvidenceRef:
        if self.document_id is None and self.candidate_id is None:
            raise ValueError("Cita sin documento ni candidato")
        return self


_SENSITIVE_PATCH_KEYS = frozenset(
    {
        "authorization",
        "cv",
        "dni",
        "document_text",
        "email",
        "password",
        "personal_email",
        "phone",
        "raw_document",
        "secret",
        "token",
    }
)


class AssistantAction(_AssistantInput):
    action_id: uuid.UUID
    type: AssistantActionType
    form_id: AssistantFormId | None = None
    route: str | None = Field(default=None, max_length=200)
    patch: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    field_origins: dict[str, FieldOrigin] = Field(default_factory=dict)
    requires_confirmation: bool = True

    @model_validator(mode="after")
    def _validate_action(self) -> AssistantAction:
        keys = set(self.patch)
        if keys - set(self.field_origins):
            raise ValueError("Campos sin origen declarado")
        if any(str(key).strip().lower() in _SENSITIVE_PATCH_KEYS for key in keys):
            raise ValueError("Campo sensible no permitido en patch")
        if not self.requires_confirmation:
            raise ValueError("Acción requiere confirmación explícita")
        if self.type is AssistantActionType.FILL_FORM:
            if self.form_id is None or not self.patch:
                raise ValueError("fill_form exige form_id y patch")
        if self.type is AssistantActionType.NAVIGATE:
            if not self.route or not self.route.startswith("/") or "://" in self.route:
                raise ValueError("navigate exige ruta interna")
        return self


class AssistantMessageResponse(_AssistantInput):
    run_id: uuid.UUID
    answer: str = Field(min_length=1, max_length=4000)
    status: Literal["pending", "completed", "needs_review", "waiting_approval", "failed"]
    citations: list[EvidenceRef] = Field(default_factory=list, max_length=10)
    proposed_actions: list[AssistantAction] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    unsupported_reason: str | None = Field(default=None, max_length=300)


class AssistantActionAck(_AssistantInput):
    schema_version: Literal["1.0"] = "1.0"
    action_id: uuid.UUID
    decision: Literal["applied", "discarded"]
    idempotency_key: str = Field(min_length=1, max_length=100)


WORKSPACE_ASSISTANT_WORKFLOW = WorkflowContract(
    workflow="workspace_assistant",
    version="1.0.0",
    nodes=(
        NodeContract(AssistantNode.RECEIVE_REQUEST, timeout_seconds=2.0),
        NodeContract(AssistantNode.RESOLVE_CONTEXT, timeout_seconds=2.0),
        NodeContract(AssistantNode.RETRIEVE_ALLOWED_FACTS, timeout_seconds=2.0),
        NodeContract(AssistantNode.DRAFT_RESPONSE, timeout_seconds=8.0, max_retries=1),
        NodeContract(AssistantNode.VALIDATE_POLICY, timeout_seconds=2.0),
        NodeContract(AssistantNode.PROPOSE_ACTIONS, timeout_seconds=2.0),
        NodeContract(AssistantNode.FINALIZE, timeout_seconds=2.0),
    ),
    allowed_tools=frozenset(tool.value for tool in AssistantTool),
    max_retries=1,
    approval_action_type="assistant_external_effect",
    interrupt_before_effects=AssistantNode.PROPOSE_ACTIONS,
    terminal_statuses=frozenset(
        {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
)
