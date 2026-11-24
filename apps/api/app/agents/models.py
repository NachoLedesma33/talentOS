from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentDomainError(ValueError):
    """Error determinista del runtime de agentes; sin mensajes con datos personales."""


class InvalidAgentTransitionError(AgentDomainError):
    """Transición de estado no permitida por el contrato del workflow."""


class AgentTenantMismatchError(AgentDomainError):
    """El contexto de organización no coincide con el recurso o el thread."""


class UnsafeAgentPayloadError(AgentDomainError):
    """Payload con claves o valores no aptos para persistencia de agente."""


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


AGENT_RUN_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.PENDING: frozenset(
        {AgentRunStatus.RUNNING, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}
    ),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.WAITING_APPROVAL,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
    AgentRunStatus.WAITING_APPROVAL: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
    AgentRunStatus.COMPLETED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
    AgentRunStatus.CANCELLED: frozenset(),
    AgentRunStatus.TIMED_OUT: frozenset(),
}


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


APPROVAL_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset({ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}),
    ApprovalStatus.APPROVED: frozenset(),
    ApprovalStatus.REJECTED: frozenset(),
}


class AgentEventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_WAITING_APPROVAL = "run.waiting_approval"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_TIMED_OUT = "run.timed_out"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    GRAPH_INTERRUPTED = "graph.interrupted"
    CHECKPOINT_SAVED = "checkpoint.saved"
    TOOL_INVOKED = "tool.invoked"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


def _empty_payload() -> dict[str, object]:
    return {}


def can_transition_agent_run(current: AgentRunStatus, target: AgentRunStatus) -> bool:
    """Indica si el contrato de estados permite la transición solicitada."""
    return target in AGENT_RUN_TRANSITIONS.get(current, frozenset())


def ensure_agent_run_transition(current: AgentRunStatus, target: AgentRunStatus) -> None:
    """Rechaza transiciones arbitrarias; los estados no son strings libres."""
    if not can_transition_agent_run(current, target):
        raise InvalidAgentTransitionError(
            f"Transición de agente no permitida: {current} -> {target}"
        )


def ensure_approval_transition(current: ApprovalStatus, target: ApprovalStatus) -> None:
    if target not in APPROVAL_TRANSITIONS.get(current, frozenset()):
        raise InvalidAgentTransitionError(
            f"Transición de aprobación no permitida: {current} -> {target}"
        )


def thread_id_for(organization_id: uuid.UUID, agent_run_id: uuid.UUID) -> str:
    """Thread de checkpoint con organización y ejecución explícitas (ADR-006)."""
    return f"org:{organization_id}:run:{agent_run_id}"


class AgentRun(Base):
    """Ejecución de un workflow; el tenant dueño del dato es `organization_id`."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(
            AgentRunStatus,
            name="agent_run_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=AgentRunStatus.PENDING,
    )
    input_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        # La clave de idempotencia es por organización: un tenant no bloquea a otro.
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_agent_runs_org_idempotency_key",
        ),
        Index("ix_agent_runs_organization_id", "organization_id"),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_correlation_id", "correlation_id"),
    )

    def transition_to(self, target: AgentRunStatus) -> None:
        ensure_agent_run_transition(self.status, target)
        self.status = target


class AgentEvent(Base):
    """Traza inspeccionable; el tenant se resuelve por la ejecución padre."""

    __tablename__ = "agent_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[AgentEventType] = mapped_column(
        SAEnum(
            AgentEventType,
            name="agent_event_type",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=_empty_payload)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        Index("ix_agent_events_agent_run_id", "agent_run_id"),
        Index("ix_agent_events_event_type", "event_type"),
        Index("ix_agent_events_created_at", "created_at"),
    )


class Approval(Base):
    """Decisión humana persistida: actor, fecha y resultado auditable."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=_empty_payload)
    status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(
            ApprovalStatus,
            name="approval_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_approvals_organization_id", "organization_id"),
        Index("ix_approvals_agent_run_id", "agent_run_id"),
        Index("ix_approvals_status", "status"),
    )

    def decide(self, target: ApprovalStatus, decided_by: uuid.UUID, decided_at: datetime) -> None:
        ensure_approval_transition(self.status, target)
        self.status = target
        self.decided_by = decided_by
        self.decided_at = decided_at


class AgentCheckpoint(Base):
    """Detalle de persistencia de `AgentRun`, no una entidad de producto (ADR-006)."""

    __tablename__ = "agent_checkpoints"

    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    checkpoint_ns: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=_empty_payload)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        # La PK compuesta es el índice único exigido para (org, thread, ns, checkpoint).
        PrimaryKeyConstraint(
            "organization_id",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            name="pk_agent_checkpoints",
        ),
        Index("ix_agent_checkpoints_agent_run_id", "agent_run_id"),
    )

    @property
    def scope_key(self) -> tuple[uuid.UUID, str, str, str]:
        return (self.organization_id, self.thread_id, self.checkpoint_ns, self.checkpoint_id)


def is_safe_payload_value(value: object) -> bool:
    """Comprueba que el valor pueda persistirse como JSON sin ORM ni clientes."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, Mapping):
        return all(isinstance(k, str) and is_safe_payload_value(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(is_safe_payload_value(item) for item in value)
    return False
