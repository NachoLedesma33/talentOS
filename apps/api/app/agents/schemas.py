from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.models import (
    AgentEventType,
    AgentRunStatus,
    ApprovalStatus,
    UnsafeAgentPayloadError,
    is_safe_payload_value,
)

# Claves que nunca deben aparecer en un payload de evento/aprobación/checkpoint.
_FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "api_key",
        "authorization",
        "chain_of_thought",
        "cv",
        "document_text",
        "password",
        "personal_email",
        "phone",
        "raw_document",
        "reasoning",
        "resume",
        "secret",
        "token",
    }
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(bearer\s+|sk-[a-z0-9]{8,}|api[_-]?key\s*[:=]|password\s*[:=])"
)
_MAX_PAYLOAD_STRING = 2000
_MAX_PAYLOAD_DEPTH = 10


def _key_is_forbidden(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    return any(
        re.search(rf"(^|_){re.escape(token)}($|_)", normalized)
        for token in _FORBIDDEN_KEY_TOKENS
    )


def _validate_payload_value(value: object, depth: int = 0) -> None:
    if depth > _MAX_PAYLOAD_DEPTH:
        raise UnsafeAgentPayloadError("Payload demasiado profundo")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _key_is_forbidden(key):
                raise UnsafeAgentPayloadError("Clave de payload no permitida")
            _validate_payload_value(item, depth + 1)
        return
    if isinstance(value, str):
        if len(value) > _MAX_PAYLOAD_STRING or _SECRET_VALUE_PATTERN.search(value):
            raise UnsafeAgentPayloadError("Valor de payload no permitido")
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise UnsafeAgentPayloadError("Valor numérico no finito en payload")
    if isinstance(value, (list, tuple, Sequence)) and not isinstance(value, (str, bytes)):
        for item in value:
            _validate_payload_value(item, depth + 1)
        return
    if not is_safe_payload_value(value):
        raise UnsafeAgentPayloadError("Valor no serializable como JSON en payload")


def validate_safe_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Copia validada: sin secretos, CV, chain-of-thought ni objetos ORM."""
    if not isinstance(payload, Mapping):
        raise UnsafeAgentPayloadError("Payload debe ser un objeto JSON")
    result: dict[str, object] = dict(payload)
    _validate_payload_value(result)
    return result


class WorkflowState(TypedDict):
    """Estado LangGraph serializable; ningún campo es objeto ORM ni cliente LLM."""

    organization_id: str
    actor_id: str
    correlation_id: str
    agent_run_id: str
    idempotency_key: str
    status: AgentRunStatus
    errors: list[dict[str, object]]
    approvals: list[dict[str, object]]


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AgentRunStart(_InputModel):
    """Arranque de ejecución; la autorización y el tenant vienen del contexto."""

    workflow: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    input_ref: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=100)
    correlation_id: uuid.UUID
    actor_id: uuid.UUID


class ApprovalDecision(_InputModel):
    """Decisión humana: quién decide y qué resultado, con aprobación pendiente."""

    approval_id: uuid.UUID
    decision: ApprovalStatus
    decided_by: uuid.UUID
    note: str | None = Field(default=None, max_length=500)

    @field_validator("decision")
    @classmethod
    def _only_decided_values(cls, value: ApprovalStatus) -> ApprovalStatus:
        if value is ApprovalStatus.PENDING:
            raise ValueError("La decisión no puede quedar pendiente")
        return value


class StartAgentRunRequest(_InputModel):
    """Request HTTP de arranque; actor, tenant y workflow los fija el servicio."""

    application_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=100)
    correlation_id: uuid.UUID | None = None


class StartOrchestrationRunRequest(_InputModel):
    """Arranque del orquestador; el workflow lo fija el endpoint, nunca el body."""

    application_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=100)
    correlation_id: uuid.UUID | None = None


class DecideApprovalRequest(_InputModel):
    """Decisión humana desde HTTP; el actor nunca viaja en el body."""

    decision: str = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)


class AgentEventCreate(_InputModel):
    """Evento de traza con payload saneado y correlación obligatoria."""

    agent_run_id: uuid.UUID
    event_type: AgentEventType
    correlation_id: uuid.UUID
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _safe_payload(cls, value: dict[str, object]) -> dict[str, object]:
        return validate_safe_payload(value)


def workflow_state(
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    correlation_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    idempotency_key: str,
    status: AgentRunStatus = AgentRunStatus.PENDING,
) -> WorkflowState:
    """Construye el estado inicial con IDs como texto y listas vacías."""
    state: WorkflowState = {
        "organization_id": str(organization_id),
        "actor_id": str(actor_id),
        "correlation_id": str(correlation_id),
        "agent_run_id": str(agent_run_id),
        "idempotency_key": idempotency_key,
        "status": status,
        "errors": [],
        "approvals": [],
    }
    return state
