from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.db.base import Base


class AutomationDomainError(ValueError):
    """Error determinista del motor de automatización; sin datos personales."""


class InvalidAutomationTransitionError(AutomationDomainError):
    """Transición de estado no permitida por el contrato de automatización."""


class AutomationTenantMismatchError(AutomationDomainError):
    """El contexto de organización no coincide con el recurso solicitado."""


class AutomationVersionImmutableError(AutomationDomainError):
    """Un snapshot versionado no puede reescribirse."""


class AutomationStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class AutomationTriggerEventType(StrEnum):
    APPLICATION_STAGE_CHANGED = "application.stage_changed"


class AutomationActionType(StrEnum):
    CREATE_TASK = "create_task"
    CREATE_MESSAGE_DRAFT = "create_message_draft"
    REQUEST_APPROVAL = "request_approval"
    RECORD_NOTE = "record_note"
    PROPOSE_STAGE_CHANGE = "propose_stage_change"
    RUN_AUTHORIZED_ANALYSIS = "run_authorized_analysis"


class AutomationRunMode(StrEnum):
    TEST = "test"
    LIVE = "live"


class AutomationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class AutomationRunEventType(StrEnum):
    TRIGGER_MATCHED = "trigger_matched"
    CONDITION_EVALUATED = "condition_evaluated"
    ACTION_PLANNED = "action_planned"
    ACTION_EXECUTED = "action_executed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DRY_RUN = "dry_run"


class AutomationApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


AUTOMATION_TRANSITIONS: dict[AutomationStatus, frozenset[AutomationStatus]] = {
    AutomationStatus.DRAFT: frozenset({AutomationStatus.ACTIVE, AutomationStatus.ARCHIVED}),
    AutomationStatus.ACTIVE: frozenset(
        {AutomationStatus.INACTIVE, AutomationStatus.ARCHIVED}
    ),
    AutomationStatus.INACTIVE: frozenset(
        {AutomationStatus.ACTIVE, AutomationStatus.ARCHIVED}
    ),
    AutomationStatus.ARCHIVED: frozenset(),
}

RUN_TRANSITIONS: dict[AutomationRunStatus, frozenset[AutomationRunStatus]] = {
    AutomationRunStatus.PENDING: frozenset(
        {AutomationRunStatus.RUNNING, AutomationRunStatus.CANCELLED}
    ),
    AutomationRunStatus.RUNNING: frozenset(
        {
            AutomationRunStatus.WAITING_APPROVAL,
            AutomationRunStatus.COMPLETED,
            AutomationRunStatus.FAILED,
            AutomationRunStatus.CANCELLED,
            AutomationRunStatus.TIMED_OUT,
        }
    ),
    AutomationRunStatus.WAITING_APPROVAL: frozenset(
        {
            AutomationRunStatus.RUNNING,
            AutomationRunStatus.CANCELLED,
            AutomationRunStatus.FAILED,
        }
    ),
    AutomationRunStatus.COMPLETED: frozenset(),
    AutomationRunStatus.FAILED: frozenset(),
    AutomationRunStatus.CANCELLED: frozenset(),
    AutomationRunStatus.TIMED_OUT: frozenset(),
}

APPROVAL_TRANSITIONS: dict[AutomationApprovalStatus, frozenset[AutomationApprovalStatus]] = {
    AutomationApprovalStatus.PENDING: frozenset(
        {AutomationApprovalStatus.APPROVED, AutomationApprovalStatus.REJECTED}
    ),
    AutomationApprovalStatus.APPROVED: frozenset(),
    AutomationApprovalStatus.REJECTED: frozenset(),
}


def _utcnow() -> datetime:
    """Timestamp UTC aplicado por Python; la BD no define reloj local."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


def _empty_payload() -> dict[str, object]:
    return {}


def ensure_automation_transition(
    current: AutomationStatus, target: AutomationStatus
) -> None:
    if target not in AUTOMATION_TRANSITIONS.get(current, frozenset()):
        raise InvalidAutomationTransitionError(
            f"Transición de automatización no permitida: {current} -> {target}"
        )


def ensure_run_transition(current: AutomationRunStatus, target: AutomationRunStatus) -> None:
    if target not in RUN_TRANSITIONS.get(current, frozenset()):
        raise InvalidAutomationTransitionError(
            f"Transición de ejecución no permitida: {current} -> {target}"
        )


def ensure_approval_transition(
    current: AutomationApprovalStatus, target: AutomationApprovalStatus
) -> None:
    if target not in APPROVAL_TRANSITIONS.get(current, frozenset()):
        raise InvalidAutomationTransitionError(
            f"Transición de aprobación no permitida: {current} -> {target}"
        )


class Automation(Base):
    """Regla del tenant con estado y versión corriente; sin lógica de negocio."""

    __tablename__ = "automations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[AutomationStatus] = mapped_column(
        SAEnum(
            AutomationStatus,
            name="automation_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=AutomationStatus.DRAFT,
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name", name="uq_automations_organization_id_name"
        ),
        CheckConstraint(
            "current_version >= 1", name="ck_automations_current_version_positive"
        ),
        CheckConstraint("length(name) <= 200", name="ck_automations_name_length"),
        Index("ix_automations_organization_id", "organization_id"),
        Index("ix_automations_status", "status"),
    )

    def transition_to(self, target: AutomationStatus) -> Automation:
        ensure_automation_transition(self.status, target)
        self.status = target
        return self


class AutomationVersion(Base):
    """Snapshot inmutable de trigger, condiciones y acciones; sin método de update."""

    __tablename__ = "automation_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automations.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    conditions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    actions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "automation_id", "version", name="uq_automation_versions_automation_version"
        ),
        CheckConstraint("version >= 1", name="ck_automation_versions_version_positive"),
        Index("ix_automation_versions_organization_id", "organization_id"),
        Index("ix_automation_versions_automation_id", "automation_id"),
    )


@event.listens_for(AutomationVersion, "before_update")
def _reject_version_update(
    _mapper: Mapper[Any], _connection: Connection, _target: AutomationVersion
) -> None:
    """Defensa de persistencia: ningún UPDATE puede reescribir un snapshot."""
    raise AutomationVersionImmutableError("Las versiones de automatización son inmutables")


class AutomationRun(Base):
    """Ejecución trazable; sin score, sin campo de decisión de contratación."""

    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automations.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[AutomationRunMode] = mapped_column(
        SAEnum(
            AutomationRunMode,
            name="automation_run_mode",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=AutomationRunMode.TEST,
    )
    status: Mapped[AutomationRunStatus] = mapped_column(
        SAEnum(
            AutomationRunStatus,
            name="automation_run_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=AutomationRunStatus.PENDING,
    )
    trigger_event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Referencia lógica al evento de dominio; sin FK a tabla mutable.
    trigger_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "automation_id", "idempotency_key", name="uq_automation_runs_automation_idem"
        ),
        CheckConstraint("version >= 1", name="ck_automation_runs_version_positive"),
        CheckConstraint(
            "length(idempotency_key) <= 100", name="ck_automation_runs_idem_length"
        ),
        CheckConstraint(
            "length(trigger_event_type) <= 100", name="ck_automation_runs_event_type_length"
        ),
        Index("ix_automation_runs_organization_id", "organization_id"),
        Index("ix_automation_runs_automation_id", "automation_id"),
        Index("ix_automation_runs_status", "status"),
        Index("ix_automation_runs_correlation_id", "correlation_id"),
    )

    def transition_to(self, target: AutomationRunStatus) -> AutomationRun:
        ensure_run_transition(self.status, target)
        self.status = target
        return self


class AutomationRunEvent(Base):
    """Historial saneado de la ejecución; nunca CV, secretos ni PII."""

    __tablename__ = "automation_run_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[AutomationRunEventType] = mapped_column(
        SAEnum(
            AutomationRunEventType,
            name="automation_run_event_type",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=_empty_payload
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_automation_run_events_organization_id", "organization_id"),
        Index("ix_automation_run_events_run_id", "run_id"),
        Index("ix_automation_run_events_event_type", "event_type"),
        Index("ix_automation_run_events_created_at", "created_at"),
    )


class AutomationApproval(Base):
    """Aprobación humana de otra ejecución; distinta de `app.agents.Approval` (ADR-012)."""

    __tablename__ = "automation_approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[AutomationActionType] = mapped_column(
        SAEnum(
            AutomationActionType,
            name="automation_action_type",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=_empty_payload
    )
    status: Mapped[AutomationApprovalStatus] = mapped_column(
        SAEnum(
            AutomationApprovalStatus,
            name="automation_approval_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=AutomationApprovalStatus.PENDING,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id", "action_type", name="uq_automation_approvals_run_action"
        ),
        CheckConstraint(
            "length(payload_hash) = 64", name="ck_automation_approvals_hash_length"
        ),
        Index("ix_automation_approvals_organization_id", "organization_id"),
        Index("ix_automation_approvals_run_id", "run_id"),
        Index("ix_automation_approvals_status", "status"),
    )

    def decide(
        self,
        target: AutomationApprovalStatus,
        decided_by: uuid.UUID,
        decided_at: datetime,
    ) -> AutomationApproval:
        ensure_approval_transition(self.status, target)
        self.status = target
        self.decided_by = decided_by
        self.decided_at = decided_at
        return self
