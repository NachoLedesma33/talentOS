from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DBSession

from app.agents.models import (
    AgentCheckpoint,
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentTenantMismatchError,
    Approval,
    ApprovalStatus,
)
from app.agents.schemas import validate_safe_payload


def get_agent_run(
    db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> AgentRun | None:
    """Lee una ejecución solo del tenant indicado."""
    stmt = select(AgentRun).where(
        AgentRun.organization_id == organization_id,
        AgentRun.id == agent_run_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_agent_run_by_idempotency_key(
    db: DBSession, organization_id: uuid.UUID, idempotency_key: str
) -> AgentRun | None:
    """Busca la ejecución existente por clave de idempotencia dentro del tenant."""
    stmt = select(AgentRun).where(
        AgentRun.organization_id == organization_id,
        AgentRun.idempotency_key == idempotency_key,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_or_create_agent_run(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    workflow: str,
    version: str,
    idempotency_key: str,
    correlation_id: uuid.UUID,
    actor_id: uuid.UUID,
    input_ref: str | None = None,
) -> AgentRun:
    """Idempotencia de persistencia: la UNIQUE del tenant evita dos ejecuciones."""
    existing = get_agent_run_by_idempotency_key(db, organization_id, idempotency_key)
    if existing is not None:
        return existing
    run = AgentRun(
        organization_id=organization_id,
        workflow=workflow,
        version=version,
        input_ref=input_ref,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        actor_id=actor_id,
        status=AgentRunStatus.PENDING,
    )
    db.add(run)
    db.flush()
    return run


def update_agent_run_status(
    db: DBSession, run: AgentRun, status: AgentRunStatus
) -> AgentRun:
    """Persiste una transición ya validada por el modelo; sin commit."""
    run.transition_to(status)
    db.flush()
    return run


def set_agent_run_output(db: DBSession, run: AgentRun, output_ref: str) -> AgentRun:
    run.output_ref = output_ref
    db.flush()
    return run


def _require_run(
    db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> AgentRun:
    run = get_agent_run(db, organization_id, agent_run_id)
    if run is None:
        raise AgentTenantMismatchError("Ejecución no disponible para la organización")
    return run


def create_agent_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    event_type: AgentEventType,
    payload: dict[str, object],
    correlation_id: uuid.UUID,
) -> AgentEvent:
    """Registra traza del tenant; valida payload sin guardar secretos ni CV."""
    _require_run(db, organization_id, agent_run_id)
    event = AgentEvent(
        agent_run_id=agent_run_id,
        event_type=event_type,
        payload=validate_safe_payload(payload),
        correlation_id=correlation_id,
    )
    db.add(event)
    db.flush()
    return event


def list_agent_events(
    db: DBSession,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentEvent]:
    """Lista eventos de una ejecución del tenant, ordenados y paginados."""
    _require_run(db, organization_id, agent_run_id)
    stmt = (
        select(AgentEvent)
        .where(
            AgentEvent.agent_run_id == agent_run_id,
        )
        .order_by(AgentEvent.created_at, AgentEvent.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def purge_agent_events(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    cutoff: datetime,
) -> int:
    """Borra traza antigua de runs terminales del tenant; sin commit."""
    run_ids = select(AgentRun.id).where(
        AgentRun.organization_id == organization_id,
        AgentRun.status.in_(
            (
                AgentRunStatus.COMPLETED,
                AgentRunStatus.FAILED,
                AgentRunStatus.CANCELLED,
                AgentRunStatus.TIMED_OUT,
            )
        ),
    )
    filters = (
        AgentEvent.agent_run_id.in_(run_ids),
        AgentEvent.created_at < cutoff,
    )
    count_stmt = select(func.count()).select_from(AgentEvent).where(*filters)
    total = int(db.execute(count_stmt).scalar_one())
    db.execute(delete(AgentEvent).where(*filters))
    db.flush()
    return total


def create_approval(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    action_type: str,
    payload: dict[str, object],
) -> Approval:
    """Crea aprobación pendiente para una ejecución del tenant."""
    _require_run(db, organization_id, agent_run_id)
    approval = Approval(
        organization_id=organization_id,
        agent_run_id=agent_run_id,
        action_type=action_type,
        payload=validate_safe_payload(payload),
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.flush()
    return approval


def get_approval(
    db: DBSession, organization_id: uuid.UUID, approval_id: uuid.UUID
) -> Approval | None:
    stmt = select(Approval).where(
        Approval.organization_id == organization_id,
        Approval.id == approval_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def decide_approval(
    db: DBSession,
    approval: Approval,
    *,
    decision: ApprovalStatus,
    decided_by: uuid.UUID,
    decided_at: datetime,
) -> Approval:
    """Persiste actor, fecha y resultado; la transición la valida el modelo."""
    approval.decide(decision, decided_by, decided_at)
    db.flush()
    return approval


def list_approvals_for_run(
    db: DBSession, organization_id: uuid.UUID, agent_run_id: uuid.UUID
) -> list[Approval]:
    """Lista aprobaciones de una ejecución del tenant, ordenadas y sin lógica de dominio."""
    stmt = (
        select(Approval)
        .where(
            Approval.organization_id == organization_id,
            Approval.agent_run_id == agent_run_id,
        )
        .order_by(Approval.created_at, Approval.id)
    )
    return list(db.execute(stmt).scalars().all())


def count_tool_invocations(
    db: DBSession,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    tool_name: str,
) -> int:
    """Cuenta eventos `tool.invoked` persistidos para aplicar rate limit."""
    events = list_agent_events(db, organization_id, agent_run_id, limit=1000)
    return sum(
        1
        for event in events
        if event.event_type == AgentEventType.TOOL_INVOKED
        and event.payload.get("tool") == tool_name
    )


def find_tool_event_by_hash(
    db: DBSession,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    tool_name: str,
    idempotency_hash: str,
) -> AgentEvent | None:
    """Busca la invocación exitosa ya persistida para reutilizar su resultado."""
    events = list_agent_events(db, organization_id, agent_run_id, limit=1000)
    for event in reversed(events):
        payload = event.payload
        if (
            event.event_type == AgentEventType.TOOL_INVOKED
            and payload.get("tool") == tool_name
            and payload.get("status") == "succeeded"
            and payload.get("idempotency_hash") == idempotency_hash
        ):
            return event
    return None


def find_approval_by_payload_hash(
    db: DBSession,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    idempotency_hash: str,
) -> Approval | None:
    """Busca la aprobación del tenant creada por una misma clave de idempotencia."""
    stmt = (
        select(Approval)
        .where(
            Approval.organization_id == organization_id,
            Approval.agent_run_id == agent_run_id,
        )
        .order_by(Approval.created_at, Approval.id)
    )
    approvals = list(db.execute(stmt).scalars().all())
    for approval in reversed(approvals):
        if approval.payload.get("idempotency_hash") == idempotency_hash:
            return approval
    return None


def get_checkpoint(
    db: DBSession,
    organization_id: uuid.UUID,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str,
) -> AgentCheckpoint | None:
    stmt = select(AgentCheckpoint).where(
        AgentCheckpoint.organization_id == organization_id,
        AgentCheckpoint.thread_id == thread_id,
        AgentCheckpoint.checkpoint_ns == checkpoint_ns,
        AgentCheckpoint.checkpoint_id == checkpoint_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def upsert_checkpoint(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str,
    payload: dict[str, object],
) -> AgentCheckpoint:
    """Escritura delgada del payload ya serializado; sin commit."""
    row = get_checkpoint(db, organization_id, thread_id, checkpoint_ns, checkpoint_id)
    if row is None:
        row = AgentCheckpoint(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
            payload=payload,
        )
        db.add(row)
    else:
        row.payload = payload
    db.flush()
    return row


def list_checkpoints(
    db: DBSession, organization_id: uuid.UUID, thread_id: str, checkpoint_ns: str
) -> list[AgentCheckpoint]:
    stmt = (
        select(AgentCheckpoint)
        .where(
            AgentCheckpoint.organization_id == organization_id,
            AgentCheckpoint.thread_id == thread_id,
            AgentCheckpoint.checkpoint_ns == checkpoint_ns,
        )
        .order_by(AgentCheckpoint.checkpoint_id)
    )
    return list(db.execute(stmt).scalars().all())


def delete_checkpoints_for_thread(
    db: DBSession, organization_id: uuid.UUID, thread_id: str
) -> None:
    stmt = delete(AgentCheckpoint).where(
        AgentCheckpoint.organization_id == organization_id,
        AgentCheckpoint.thread_id == thread_id,
    )
    db.execute(stmt)
    db.flush()
