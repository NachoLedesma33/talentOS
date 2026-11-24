from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.applications.models import Application, StageChange
from app.automation.models import (
    Automation,
    AutomationActionType,
    AutomationApproval,
    AutomationApprovalStatus,
    AutomationRun,
    AutomationRunEvent,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationRunStatus,
    AutomationStatus,
    AutomationTenantMismatchError,
    AutomationTriggerEventType,
    AutomationVersion,
)


def get_automation(
    db: DBSession, organization_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation | None:
    """Lee una automatización solo si pertenece al tenant autenticado."""
    stmt = select(Automation).where(
        Automation.organization_id == organization_id,
        Automation.id == automation_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_automations(
    db: DBSession,
    organization_id: uuid.UUID,
    status: AutomationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Automation]:
    """Lista del tenant con filtros acotados y paginación; sin lógica de negocio."""
    stmt = select(Automation).where(Automation.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Automation.status == status)
    stmt = stmt.order_by(Automation.created_at, Automation.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def _require_automation(
    db: DBSession, organization_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation:
    automation = get_automation(db, organization_id, automation_id)
    if automation is None:
        raise AutomationTenantMismatchError("La automatización no pertenece a la organización")
    return automation


def next_version(
    db: DBSession, organization_id: uuid.UUID, automation_id: uuid.UUID
) -> int:
    """Siguiente versión disponible para una automatización del tenant."""
    _require_automation(db, organization_id, automation_id)
    stmt = select(func.coalesce(func.max(AutomationVersion.version), 0)).where(
        AutomationVersion.organization_id == organization_id,
        AutomationVersion.automation_id == automation_id,
    )
    return int(db.scalar(stmt) or 0) + 1


def create_version(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    automation_id: uuid.UUID,
    version: int,
    trigger: Mapping[str, object],
    conditions: Sequence[Mapping[str, object]],
    actions: Sequence[Mapping[str, object]],
    created_by: uuid.UUID,
) -> AutomationVersion:
    """Persiste un snapshot saneado; el tenant de la automatización se verifica."""
    _require_automation(db, organization_id, automation_id)
    snapshot = AutomationVersion(
        organization_id=organization_id,
        automation_id=automation_id,
        version=version,
        trigger=validate_safe_payload(trigger),
        conditions=[validate_safe_payload(item) for item in conditions],
        actions=[validate_safe_payload(item) for item in actions],
        created_by=created_by,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def get_version(
    db: DBSession, organization_id: uuid.UUID, automation_id: uuid.UUID, version: int
) -> AutomationVersion | None:
    """Lee una versión concreta solo dentro del tenant."""
    stmt = select(AutomationVersion).where(
        AutomationVersion.organization_id == organization_id,
        AutomationVersion.automation_id == automation_id,
        AutomationVersion.version == version,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_run_by_key(
    db: DBSession,
    organization_id: uuid.UUID,
    automation_id: uuid.UUID,
    idempotency_key: str,
) -> AutomationRun | None:
    """Busca la ejecución idempotente de esa automatización dentro del tenant."""
    stmt = select(AutomationRun).where(
        AutomationRun.organization_id == organization_id,
        AutomationRun.automation_id == automation_id,
        AutomationRun.idempotency_key == idempotency_key,
    )
    return db.execute(stmt).scalar_one_or_none()


def create_run(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    automation_id: uuid.UUID,
    version: int,
    mode: AutomationRunMode,
    trigger_event_type: AutomationTriggerEventType,
    trigger_event_id: uuid.UUID,
    idempotency_key: str,
    correlation_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> AutomationRun:
    """Inscribe una ejecución pendiente; la UNIQUE evita duplicados por clave."""
    _require_automation(db, organization_id, automation_id)
    run = AutomationRun(
        organization_id=organization_id,
        automation_id=automation_id,
        version=version,
        mode=mode,
        status=AutomationRunStatus.PENDING,
        trigger_event_type=str(trigger_event_type.value),
        trigger_event_id=trigger_event_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        actor_id=actor_id,
    )
    db.add(run)
    db.flush()
    return run


def get_run(
    db: DBSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> AutomationRun | None:
    """Lee una ejecución solo dentro del tenant autenticado."""
    stmt = select(AutomationRun).where(
        AutomationRun.organization_id == organization_id,
        AutomationRun.id == run_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def _require_run(
    db: DBSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> AutomationRun:
    run = get_run(db, organization_id, run_id)
    if run is None:
        raise AutomationTenantMismatchError("La ejecución no pertenece a la organización")
    return run


def update_run_status(
    db: DBSession,
    organization_id: uuid.UUID,
    run: AutomationRun,
    status: AutomationRunStatus,
    *,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    error_code: str | None = None,
) -> AutomationRun:
    """Aplica una transición válida al tenant dueño de la ejecución."""
    if run.organization_id != organization_id:
        raise AutomationTenantMismatchError("La ejecución no pertenece a la organización")
    run.transition_to(status)
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at
    if error_code is not None:
        run.error_code = error_code
    db.flush()
    return run


def create_run_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    event_type: AutomationRunEventType,
    payload: Mapping[str, object],
) -> AutomationRunEvent:
    """Traza de ejecución con payload saneado; sin CV, secretos ni PII."""
    _require_run(db, organization_id, run_id)
    event = AutomationRunEvent(
        organization_id=organization_id,
        run_id=run_id,
        event_type=event_type,
        payload=validate_safe_payload(payload),
    )
    db.add(event)
    db.flush()
    return event


def list_run_events(
    db: DBSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[AutomationRunEvent]:
    """Historial de la ejecución ordenado por fecha dentro del tenant."""
    stmt = (
        select(AutomationRunEvent)
        .where(
            AutomationRunEvent.organization_id == organization_id,
            AutomationRunEvent.run_id == run_id,
        )
        .order_by(AutomationRunEvent.created_at, AutomationRunEvent.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def get_run_event_by_action_id(
    db: DBSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    action_id: str,
) -> AutomationRunEvent | None:
    """Busca la traza de una acción ya registrada para evitar duplicados."""
    for event in list_run_events(db, organization_id, run_id, limit=100):
        if event.payload.get("action_id") == action_id:
            return event
    return None


def get_stage_change(
    db: DBSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> StageChange | None:
    """Lee el evento de dominio solo si su postulación pertenece al tenant."""
    stmt = (
        select(StageChange)
        .join(Application, Application.id == StageChange.application_id)
        .where(
            Application.organization_id == organization_id,
            StageChange.id == event_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_runs(
    db: DBSession,
    organization_id: uuid.UUID,
    automation_id: uuid.UUID | None = None,
    status: AutomationRunStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AutomationRun]:
    """Lista ejecuciones del tenant; todas las consultas llevan filtro de organización."""
    stmt = select(AutomationRun).where(AutomationRun.organization_id == organization_id)
    if automation_id is not None:
        stmt = stmt.where(AutomationRun.automation_id == automation_id)
    if status is not None:
        stmt = stmt.where(AutomationRun.status == status)
    stmt = stmt.order_by(AutomationRun.created_at, AutomationRun.id).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def _payload_hash(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_approval(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    action_type: AutomationActionType,
    payload: Mapping[str, object],
    created_by: uuid.UUID,
) -> AutomationApproval:
    """Solicita aprobación humana con hash del payload saneado que se presenta."""
    _require_run(db, organization_id, run_id)
    safe_payload = validate_safe_payload(payload)
    approval = AutomationApproval(
        organization_id=organization_id,
        run_id=run_id,
        action_type=action_type,
        payload_hash=_payload_hash(safe_payload),
        payload=safe_payload,
        created_by=created_by,
    )
    db.add(approval)
    db.flush()
    return approval


def get_approval(
    db: DBSession, organization_id: uuid.UUID, approval_id: uuid.UUID
) -> AutomationApproval | None:
    """Lee una aprobación solo si pertenece al tenant autenticado."""
    stmt = select(AutomationApproval).where(
        AutomationApproval.organization_id == organization_id,
        AutomationApproval.id == approval_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def decide_approval(
    db: DBSession,
    organization_id: uuid.UUID,
    approval: AutomationApproval,
    decision: AutomationApprovalStatus,
    decided_by: uuid.UUID,
    decided_at: datetime,
) -> AutomationApproval:
    """Registra quién y cuándo decidió; la transición se valida en el modelo."""
    if approval.organization_id != organization_id:
        raise AutomationTenantMismatchError("La aprobación no pertenece a la organización")
    approval.decide(decision, decided_by, decided_at)
    db.flush()
    return approval


def list_approvals_for_run(
    db: DBSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[AutomationApproval]:
    """Aprobaciones de una ejecución del tenant, ordenadas por creación."""
    stmt = (
        select(AutomationApproval)
        .where(
            AutomationApproval.organization_id == organization_id,
            AutomationApproval.run_id == run_id,
        )
        .order_by(AutomationApproval.created_at, AutomationApproval.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())
