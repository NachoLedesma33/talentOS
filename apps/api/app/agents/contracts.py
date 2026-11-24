"""Contratos explícitos de los dos workflows reales de la Fase 6.

No hay registro genérico de agentes: este módulo describe exactamente los grafos
implementados en `app.agents.workflow` y `app.agents.orchestrator` (SDD 9.3,
ADR-006). Las tools listadas son subset del registry de `app.agents.tools`;
ningún documento puede ampliar esta lista ni los permisos por nodo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


WorkflowNodeName = MatchingNode | OrchestrationNode


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
