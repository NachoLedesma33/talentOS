"""Contrato del único workflow real de la Fase 6: `matching_review` v1.1.0.

No hay registro genérico de agentes: este módulo describe exactamente el grafo
implementado en `app.agents.workflow` (SDD 9.3, ADR-006). Las tools listadas
son las únicas definidas en `app.agents.tools`; ningún documento puede ampliar
esta lista ni los permisos por nodo.
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


@dataclass(frozen=True)
class NodeContract:
    """Límite ejecutable por nodo: timeout y reintentos acotados."""

    name: MatchingNode
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
    interrupt_before_effects: MatchingNode
    terminal_statuses: frozenset[AgentRunStatus]

    def node(self, name: MatchingNode) -> NodeContract:
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
