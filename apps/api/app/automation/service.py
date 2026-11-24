"""Servicio de dominio del motor de automatización.

Autoridad: backend. Toda operación verifica membresía activa y rol antes de
leer recursos; el tenant nunca se toma del cliente. Ninguna aprobación se
resuelve automáticamente y ningún payload viaja a `AuditLog`.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import ValidationError
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.applications.models import ApplicationStage
from app.applications.repositories import get_application as get_application_row
from app.audit.service import record_audit
from app.automation.actions import apply_approved_action
from app.automation.conditions import AutomationEventContext
from app.automation.engine import execute_run
from app.automation.models import (
    Automation,
    AutomationActionType,
    AutomationApproval,
    AutomationApprovalStatus,
    AutomationDomainError,
    AutomationRun,
    AutomationRunEvent,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationRunStatus,
    AutomationStatus,
    AutomationTenantMismatchError,
    AutomationVersion,
)
from app.automation.repositories import (
    create_run,
    create_run_event,
    create_version,
    get_approval,
    get_automation,
    get_run,
    get_run_by_key,
    get_stage_change,
    get_version,
    list_approvals_for_run,
    next_version,
    update_run_status,
)
from app.automation.repositories import (
    decide_approval as persist_approval_decision,
)
from app.automation.repositories import (
    list_automations as list_automation_rows,
)
from app.automation.repositories import (
    list_run_events as list_automation_run_events,
)
from app.automation.repositories import (
    list_runs as list_automation_runs,
)
from app.automation.schemas import AutomationTrigger, AutomationVersionCreate
from app.identity.models import MembershipRole, User, UserStatus
from app.identity.repositories import get_membership
from app.jobs.repositories import get_job as get_job_row

_WRITE_ROLES = frozenset(
    {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.RECRUITER}
)
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_MAX_KEY_LENGTH = 100
_MAX_PAGE = 100
_MAX_APPROVALS = 10
_RESOURCE_AUTOMATION = "automation"
_RESOURCE_RUN = "automation_run"
_RESOURCE_APPROVAL = "automation_approval"


class AutomationServiceError(AutomationDomainError):
    """Error determinista con código estable; sin datos de candidatos."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _role(value: MembershipRole | str) -> MembershipRole:
    if isinstance(value, MembershipRole):
        return value
    try:
        return MembershipRole(str(value))
    except ValueError:
        raise AutomationServiceError("invalid_role") from None


def _require_actor(
    db: DBSession,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    *,
    write: bool,
) -> MembershipRole:
    """Verifica tenant, membresía activa y rol antes de cualquier lectura."""
    membership = get_membership(db, actor_id, organization_id)
    if membership is None:
        raise AutomationTenantMismatchError("Actor no disponible para la organización")
    role = _role(actor_role)
    if membership.role is not role:
        raise AutomationServiceError("permission_denied")
    if write and role not in _WRITE_ROLES:
        raise AutomationServiceError("permission_denied")
    user = db.get(User, actor_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise AutomationServiceError("permission_denied")
    return role


def _require_automation(
    db: DBSession, organization_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation:
    automation = get_automation(db, organization_id, automation_id)
    if automation is None:
        raise AutomationServiceError("automation_not_found")
    return automation


def _require_run(
    db: DBSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> AutomationRun:
    run = get_run(db, organization_id, run_id)
    if run is None:
        raise AutomationServiceError("run_not_found")
    return run


def _stage(value: ApplicationStage | str | None) -> ApplicationStage | None:
    if value is None:
        return None
    if isinstance(value, ApplicationStage):
        return value
    try:
        return ApplicationStage(str(value))
    except ValueError:
        raise AutomationServiceError("invalid_event") from None


def _decision(value: AutomationApprovalStatus | str) -> AutomationApprovalStatus:
    if isinstance(value, AutomationApprovalStatus):
        result = value
    else:
        try:
            result = AutomationApprovalStatus(str(value))
        except ValueError:
            raise AutomationServiceError("invalid_decision") from None
    if result is AutomationApprovalStatus.PENDING:
        raise AutomationServiceError("invalid_decision")
    return result


def _require_key(key: str) -> str:
    clean = key.strip()
    if not 1 <= len(clean) <= _MAX_KEY_LENGTH or _KEY_PATTERN.fullmatch(clean) is None:
        raise AutomationServiceError("invalid_idempotency_key")
    return clean


def _event_payload(
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    trigger_event_id: uuid.UUID,
    correlation_id: uuid.UUID,
    from_stage: ApplicationStage | None,
    to_stage: ApplicationStage,
    job_status: StrEnum | str,
) -> AutomationEventContext:
    payload: dict[str, object] = {
        "event_type": "application.stage_changed",
        "application_id": application_id,
        "trigger_event_id": trigger_event_id,
        "correlation_id": correlation_id,
        "from_stage": from_stage.value if from_stage is not None else None,
        "to_stage": to_stage.value,
        "job_status": str(job_status.value if isinstance(job_status, StrEnum) else job_status),
    }
    try:
        return AutomationEventContext.model_validate(payload)
    except (ValidationError, ValueError):
        raise AutomationServiceError("invalid_event") from None


def _audit_approval_requests(
    db: DBSession,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    approval_ids: list[uuid.UUID],
) -> None:
    for approval_id in approval_ids:
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="automation.approval_requested",
            resource_type=_RESOURCE_APPROVAL,
            resource_id=approval_id,
        )


def _audit_outcome(
    db: DBSession,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    run: AutomationRun,
    *,
    test_mode: bool,
    new_approval_ids: list[uuid.UUID],
) -> None:
    _audit_approval_requests(db, organization_id, actor_id, new_approval_ids)
    if test_mode:
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="automation.test_executed",
            resource_type=_RESOURCE_RUN,
            resource_id=run.id,
        )
    actions: dict[AutomationRunStatus, str] = {
        AutomationRunStatus.COMPLETED: "automation.run_completed",
        AutomationRunStatus.FAILED: "automation.run_failed",
        AutomationRunStatus.CANCELLED: "automation.run_cancelled",
        AutomationRunStatus.TIMED_OUT: "automation.run_failed",
    }
    action = actions.get(run.status)
    if action is not None:
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type=_RESOURCE_RUN,
            resource_id=run.id,
        )


def _start_for_automation(
    db: DBSession,
    automation: Automation,
    *,
    actor_id: uuid.UUID,
    mode: AutomationRunMode,
    idempotency_key: str,
    context: AutomationEventContext,
) -> AutomationRun:
    """Crea una sola ejecución por clave y la ejecuta con el snapshot exacto."""
    existing = get_run_by_key(
        db, automation.organization_id, automation.id, idempotency_key
    )
    if existing is not None:
        return existing
    version = get_version(
        db, automation.organization_id, automation.id, automation.current_version
    )
    if version is None:
        raise AutomationServiceError("version_not_found")
    run = create_run(
        db,
        organization_id=automation.organization_id,
        automation_id=automation.id,
        version=automation.current_version,
        mode=mode,
        trigger_event_type=context.event_type,
        trigger_event_id=context.trigger_event_id,
        idempotency_key=idempotency_key,
        correlation_id=context.correlation_id,
        actor_id=actor_id,
    )
    create_run_event(
        db,
        organization_id=automation.organization_id,
        run_id=run.id,
        event_type=AutomationRunEventType.TRIGGER_MATCHED,
        payload=validate_safe_payload(context.model_dump(mode="json")),
    )
    record_audit(
        db,
        organization_id=automation.organization_id,
        actor_id=actor_id,
        action="automation.run_started",
        resource_type=_RESOURCE_RUN,
        resource_id=run.id,
    )
    before = {
        approval.id
        for approval in list_approvals_for_run(
            db, automation.organization_id, run.id, limit=_MAX_APPROVALS
        )
    }
    result = execute_run(db, run, actor_id=actor_id)
    after = list_approvals_for_run(
        db, automation.organization_id, run.id, limit=_MAX_APPROVALS
    )
    new_ids = [approval.id for approval in after if approval.id not in before]
    _audit_outcome(
        db,
        automation.organization_id,
        actor_id,
        result,
        test_mode=mode is AutomationRunMode.TEST,
        new_approval_ids=new_ids,
    )
    return result


def create_automation(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    name: str,
    version: AutomationVersionCreate,
) -> Automation:
    """Alta en `draft` con versión 1 inmutable; el nombre no incluye datos de candidato."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    clean_name = name.strip()
    if not 1 <= len(clean_name) <= 200:
        raise AutomationServiceError("invalid_name")
    automation = Automation(
        organization_id=organization_id,
        name=clean_name,
        status=AutomationStatus.DRAFT,
        current_version=1,
        created_by=actor_id,
    )
    db.add(automation)
    db.flush()
    snapshot = version.to_snapshot()
    create_version(
        db,
        organization_id=organization_id,
        automation_id=automation.id,
        version=1,
        trigger=snapshot["trigger"],  # type: ignore[arg-type]
        conditions=snapshot["conditions"],  # type: ignore[arg-type]
        actions=snapshot["actions"],  # type: ignore[arg-type]
        created_by=actor_id,
    )
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="automation.created",
        resource_type=_RESOURCE_AUTOMATION,
        resource_id=automation.id,
    )
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="automation.version_created",
        resource_type=_RESOURCE_AUTOMATION,
        resource_id=automation.id,
    )
    db.commit()
    return automation


def add_version(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID,
    version: AutomationVersionCreate,
) -> AutomationVersion:
    """Congela un nuevo snapshot y hace que sea la versión corriente."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    automation = _require_automation(db, organization_id, automation_id)
    number = next_version(db, organization_id, automation.id)
    snapshot = version.to_snapshot()
    created = create_version(
        db,
        organization_id=organization_id,
        automation_id=automation.id,
        version=number,
        trigger=snapshot["trigger"],  # type: ignore[arg-type]
        conditions=snapshot["conditions"],  # type: ignore[arg-type]
        actions=snapshot["actions"],  # type: ignore[arg-type]
        created_by=actor_id,
    )
    automation.current_version = number
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="automation.version_created",
        resource_type=_RESOURCE_AUTOMATION,
        resource_id=automation.id,
    )
    db.commit()
    return created


def activate_automation(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID,
) -> Automation:
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    automation = _require_automation(db, organization_id, automation_id)
    automation.transition_to(AutomationStatus.ACTIVE)
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="automation.activated",
        resource_type=_RESOURCE_AUTOMATION,
        resource_id=automation.id,
    )
    db.commit()
    return automation


def deactivate_automation(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID,
) -> Automation:
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    automation = _require_automation(db, organization_id, automation_id)
    automation.transition_to(AutomationStatus.INACTIVE)
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="automation.deactivated",
        resource_type=_RESOURCE_AUTOMATION,
        resource_id=automation.id,
    )
    db.commit()
    return automation


def _start_run(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID,
    mode: AutomationRunMode,
    idempotency_key: str,
    application_id: uuid.UUID,
    from_stage: ApplicationStage | str | None,
    to_stage: ApplicationStage | str | None,
    trigger_event_id: uuid.UUID | None,
    correlation_id: uuid.UUID | None,
) -> AutomationRun:
    """Valida el evento real y delega la ejecución; clave repetida = misma run."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    key = _require_key(idempotency_key)
    existing = get_run_by_key(db, organization_id, automation_id, key)
    if existing is not None:
        return existing
    automation = _require_automation(db, organization_id, automation_id)
    if automation.status is AutomationStatus.ARCHIVED:
        raise AutomationServiceError("automation_archived")
    application = get_application_row(db, organization_id, application_id)
    if application is None:
        raise AutomationTenantMismatchError("La postulación no pertenece a la organización")
    job = get_job_row(db, organization_id, application.job_id)
    if job is None:
        raise AutomationTenantMismatchError("La vacante no pertenece a la organización")

    resolved_from = _stage(from_stage)
    resolved_to = _stage(to_stage)
    event_id = trigger_event_id
    if event_id is not None:
        change = get_stage_change(db, organization_id, event_id)
        if change is None or change.application_id != application.id:
            raise AutomationTenantMismatchError("El evento no pertenece a la organización")
        resolved_from = _stage(change.from_stage)
        resolved_to = _stage(change.to_stage)
    else:
        event_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"automation|{organization_id}|{automation_id}|{key}"
        )
    if resolved_to is None:
        resolved_to = application.stage
    if resolved_from is None:
        resolved_from = application.stage

    correlation = correlation_id or uuid.uuid5(
        uuid.NAMESPACE_URL, f"automation|correlation|{key}"
    )
    context = _event_payload(
        organization_id=organization_id,
        application_id=application.id,
        trigger_event_id=event_id,
        correlation_id=correlation,
        from_stage=resolved_from,
        to_stage=resolved_to,
        job_status=job.status,
    )
    result = _start_for_automation(
        db,
        automation,
        actor_id=actor_id,
        mode=mode,
        idempotency_key=key,
        context=context,
    )
    db.commit()
    return result


def test_automation(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID,
    idempotency_key: str,
    application_id: uuid.UUID,
    from_stage: ApplicationStage | str | None = None,
    to_stage: ApplicationStage | str | None = None,
    trigger_event_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> AutomationRun:
    """Modo prueba: solo traza; sin aprobaciones, análisis ni cambios de etapa."""
    return _start_run(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_role=actor_role,
        automation_id=automation_id,
        mode=AutomationRunMode.TEST,
        idempotency_key=idempotency_key,
        application_id=application_id,
        from_stage=from_stage,
        to_stage=to_stage,
        trigger_event_id=trigger_event_id,
        correlation_id=correlation_id,
    )


def run_manual(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID,
    idempotency_key: str,
    application_id: uuid.UUID,
    from_stage: ApplicationStage | str | None = None,
    to_stage: ApplicationStage | str | None = None,
    trigger_event_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> AutomationRun:
    """Ejecución manual en vivo con la misma clave y límites que el modo prueba."""
    return _start_run(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_role=actor_role,
        automation_id=automation_id,
        mode=AutomationRunMode.LIVE,
        idempotency_key=idempotency_key,
        application_id=application_id,
        from_stage=from_stage,
        to_stage=to_stage,
        trigger_event_id=trigger_event_id,
        correlation_id=correlation_id,
    )


def dispatch_domain_event(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    trigger_event_id: uuid.UUID,
    correlation_id: uuid.UUID | None = None,
) -> list[AutomationRun]:
    """Dispara como máximo una ejecución por automatización activa y evento."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    change = get_stage_change(db, organization_id, trigger_event_id)
    if change is None:
        raise AutomationTenantMismatchError("El evento no pertenece a la organización")
    application = get_application_row(db, organization_id, change.application_id)
    if application is None:
        raise AutomationTenantMismatchError("La postulación no pertenece a la organización")
    job = get_job_row(db, organization_id, application.job_id)
    if job is None:
        raise AutomationTenantMismatchError("La vacante no pertenece a la organización")
    context = _event_payload(
        organization_id=organization_id,
        application_id=application.id,
        trigger_event_id=change.id,
        correlation_id=correlation_id or change.id,
        from_stage=_stage(change.from_stage),
        to_stage=_stage(change.to_stage) or application.stage,
        job_status=job.status,
    )
    runs: list[AutomationRun] = []
    automations = list_automation_rows(
        db, organization_id, status=AutomationStatus.ACTIVE, limit=_MAX_PAGE
    )
    for automation in automations:
        version = get_version(db, organization_id, automation.id, automation.current_version)
        if version is None:
            continue
        try:
            AutomationTrigger.model_validate(version.trigger)
        except (ValidationError, ValueError):
            continue
        runs.append(
            _start_for_automation(
                db,
                automation,
                actor_id=actor_id,
                mode=AutomationRunMode.LIVE,
                idempotency_key=f"event:{change.id}",
                context=context,
            )
        )
    db.commit()
    return runs


def decide_approval(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    approval_id: uuid.UUID,
    decision: AutomationApprovalStatus | str,
) -> AutomationApproval:
    """Decisión humana explícita: aprobar aplica el efecto; rechazar no aplica nada."""
    _require_actor(db, organization_id, actor_id, actor_role, write=True)
    target = _decision(decision)
    approval = get_approval(db, organization_id, approval_id)
    if approval is None:
        raise AutomationTenantMismatchError("La aprobación no pertenece a la organización")
    run = _require_run(db, organization_id, approval.run_id)
    decided_at = datetime.now(UTC)
    persist_approval_decision(
        db, organization_id, approval, target, actor_id, decided_at
    )
    resolved = dict(approval.payload)
    resolved.update(
        {
            "organization_id": str(organization_id),
            "run_id": str(run.id),
            "correlation_id": str(run.correlation_id),
            "approval_id": str(approval.id),
            "action_type": approval.action_type.value,
            "decision": target.value,
        }
    )
    create_run_event(
        db,
        organization_id=organization_id,
        run_id=run.id,
        event_type=AutomationRunEventType.APPROVAL_RESOLVED,
        payload=validate_safe_payload(resolved),
    )
    if target is AutomationApprovalStatus.REJECTED:
        update_run_status(
            db,
            organization_id,
            run,
            AutomationRunStatus.CANCELLED,
            finished_at=decided_at,
        )
        create_run_event(
            db,
            organization_id=organization_id,
            run_id=run.id,
            event_type=AutomationRunEventType.CANCELLED,
            payload=validate_safe_payload(resolved),
        )
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="automation.run_cancelled",
            resource_type=_RESOURCE_RUN,
            resource_id=run.id,
        )
    else:
        effect = apply_approved_action(
            db,
            organization_id=organization_id,
            run=run,
            approval=approval,
            actor_id=actor_id,
        )
        if not effect.applied:
            update_run_status(
                db,
                organization_id,
                run,
                AutomationRunStatus.FAILED,
                finished_at=decided_at,
                error_code=effect.reason_code.value,
            )
            create_run_event(
                db,
                organization_id=organization_id,
                run_id=run.id,
                event_type=AutomationRunEventType.FAILED,
                payload=validate_safe_payload(
                    {"reason_code": effect.reason_code.value}
                ),
            )
            record_audit(
                db,
                organization_id=organization_id,
                actor_id=actor_id,
                action="automation.run_failed",
                resource_type=_RESOURCE_RUN,
                resource_id=run.id,
            )
        else:
            applied_payload: dict[str, object] = dict(resolved)
            applied_payload["resource_id"] = (
                str(effect.resource_id) if effect.resource_id is not None else None
            )
            create_run_event(
                db,
                organization_id=organization_id,
                run_id=run.id,
                event_type=AutomationRunEventType.ACTION_EXECUTED,
                payload=validate_safe_payload(applied_payload),
            )
            if (
                approval.action_type is AutomationActionType.PROPOSE_STAGE_CHANGE
                and effect.resource_id is not None
            ):
                record_audit(
                    db,
                    organization_id=organization_id,
                    actor_id=actor_id,
                    action="automation.stage_change_applied",
                    resource_type="application",
                    resource_id=effect.resource_id,
                )
        pending = [
            item
            for item in list_approvals_for_run(
                db, organization_id, run.id, limit=_MAX_APPROVALS
            )
            if item.status is AutomationApprovalStatus.PENDING
        ]
        if not pending and run.status is AutomationRunStatus.WAITING_APPROVAL:
            update_run_status(
                db, organization_id, run, AutomationRunStatus.RUNNING
            )
            update_run_status(
                db,
                organization_id,
                run,
                AutomationRunStatus.COMPLETED,
                finished_at=decided_at,
            )
            create_run_event(
                db,
                organization_id=organization_id,
                run_id=run.id,
                event_type=AutomationRunEventType.COMPLETED,
                payload=validate_safe_payload(resolved),
            )
            record_audit(
                db,
                organization_id=organization_id,
                actor_id=actor_id,
                action="automation.run_completed",
                resource_type=_RESOURCE_RUN,
                resource_id=run.id,
            )
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="automation.approval_decided",
        resource_type=_RESOURCE_APPROVAL,
        resource_id=approval.id,
    )
    db.commit()
    return approval


def list_automations(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    status: AutomationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Automation]:
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    return list_automation_rows(
        db, organization_id, status=status, limit=min(limit, _MAX_PAGE), offset=offset
    )


def list_runs(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    automation_id: uuid.UUID | None = None,
    status: AutomationRunStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AutomationRun]:
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    return list_automation_runs(
        db,
        organization_id,
        automation_id=automation_id,
        status=status,
        limit=min(limit, _MAX_PAGE),
        offset=offset,
    )


def get_run_detail(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    run_id: uuid.UUID,
) -> AutomationRun:
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    return _require_run(db, organization_id, run_id)


def list_run_events(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    run_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[AutomationRunEvent]:
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    _require_run(db, organization_id, run_id)
    return list_automation_run_events(
        db, organization_id, run_id, limit=min(limit, _MAX_PAGE), offset=offset
    )


def list_approvals(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole | str,
    run_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[AutomationApproval]:
    _require_actor(db, organization_id, actor_id, actor_role, write=False)
    _require_run(db, organization_id, run_id)
    return list_approvals_for_run(
        db, organization_id, run_id, limit=min(limit, _MAX_PAGE), offset=offset
    )


__all__ = [
    "activate_automation",
    "add_version",
    "create_automation",
    "deactivate_automation",
    "decide_approval",
    "dispatch_domain_event",
    "get_run_detail",
    "list_approvals",
    "list_automations",
    "list_run_events",
    "list_runs",
    "run_manual",
    "test_automation",
]
