"""Motor de ejecución de automatizaciones: determinista, trazable e idempotente.

`mode=test` solo produce traza. `mode=live` aplica acciones cerradas y deja
aprobaciones persistentes antes de cualquier comunicación o cambio sensible.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session as DBSession

from app.automation.actions import (
    ActionContext,
    ActionReasonCode,
    ActionResult,
    ActionStatus,
    derive_action_id,
    execute_action,
    plan_action,
)
from app.automation.conditions import (
    AutomationEventContext,
    ConditionReasonCode,
    evaluate_conditions,
    normalize_event_payload,
)
from app.automation.models import (
    AutomationDomainError,
    AutomationRun,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationRunStatus,
)
from app.automation.repositories import (
    create_approval,
    create_run_event,
    get_run_event_by_action_id,
    get_version,
    list_approvals_for_run,
    list_run_events,
    update_run_status,
)
from app.automation.schemas import AutomationAction, AutomationCondition, AutomationTrigger
from app.core.logging import log_structured
from app.identity.models import User, UserStatus
from app.identity.repositories import get_membership
from app.llm.provider import LLMProvider, ProviderError

_ACTION_TIMEOUT_SECONDS = 2.0
_MAX_APPROVALS = 10


class AutomationEngineError(AutomationDomainError):
    """Error acotado del motor; `code` es estable y exponible sin stack trace."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require_actor(db: DBSession, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Defensa en profundidad: el ejecutor debe ser miembro activo del tenant."""
    membership = get_membership(db, actor_id, organization_id)
    user = db.get(User, actor_id)
    if membership is None or user is None or user.status is not UserStatus.ACTIVE:
        raise AutomationEngineError("actor_not_authorized")


def _emit(
    db: DBSession,
    run: AutomationRun,
    event_type: AutomationRunEventType,
    payload: dict[str, object],
) -> None:
    safe = dict(payload)
    safe["organization_id"] = str(run.organization_id)
    safe["run_id"] = str(run.id)
    safe["correlation_id"] = str(run.correlation_id)
    create_run_event(
        db,
        organization_id=run.organization_id,
        run_id=run.id,
        event_type=event_type,
        payload=safe,
    )


def _load_event(db: DBSession, run: AutomationRun) -> AutomationEventContext:
    events = list_run_events(db, run.organization_id, run.id, limit=100)
    trigger = next(
        (event for event in events if event.event_type is AutomationRunEventType.TRIGGER_MATCHED),
        None,
    )
    if trigger is None:
        raise AutomationEngineError("trigger_payload_missing")
    try:
        return normalize_event_payload(trigger.payload)
    except (ValidationError, ValueError):
        raise AutomationEngineError("invalid_trigger_payload") from None


def _failure_code(exc: Exception) -> ActionReasonCode:
    if isinstance(exc, TimeoutError):
        return ActionReasonCode.ACTION_TIMEOUT
    if isinstance(exc, ProviderError):
        return ActionReasonCode.PROVIDER_FAILED
    return ActionReasonCode.ACTION_FAILED


def _attempt(context: ActionContext) -> ActionResult:
    started = time.monotonic()
    result = execute_action(context)
    elapsed = time.monotonic() - started
    if elapsed > _ACTION_TIMEOUT_SECONDS:
        # La duración se mide con reloj monotónico; nunca se guarda el error crudo.
        raise TimeoutError(ActionReasonCode.ACTION_TIMEOUT.value)
    return result


def _execute_with_retry(context: ActionContext) -> ActionResult:
    """Un reintento como máximo; `retry_scheduled` sin mensaje ni stack trace."""
    try:
        return _attempt(context)
    except Exception as first:
        _emit(
            context.db,
            context.run,
            AutomationRunEventType.RETRY_SCHEDULED,
            {
                "action_id": str(context.action_id),
                "action_type": context.action.type.value,
                "action_index": context.index,
                "reason_code": _failure_code(first).value,
                "attempt": 1,
            },
        )
        try:
            return _attempt(context)
        except Exception as second:
            return ActionResult(
                type=context.action.type,
                status=ActionStatus.FAILED,
                resource_id=None,
                reason_code=_failure_code(second),
                event_payload={"action_id": str(context.action_id)},
            )


def _fail_run(db: DBSession, run: AutomationRun, reason_code: str) -> AutomationRun:
    log_structured(
        logging.WARNING,
        "automation.run_failed",
        correlation_id=str(run.correlation_id),
        organization_id=str(run.organization_id),
    )
    update_run_status(
        db,
        run.organization_id,
        run,
        AutomationRunStatus.FAILED,
        finished_at=datetime.now(UTC),
        error_code=reason_code[:100],
    )
    _emit(
        db,
        run,
        AutomationRunEventType.FAILED,
        {"reason_code": reason_code[:60], "status": AutomationRunStatus.FAILED.value},
    )
    return run


def _finish_completed(db: DBSession, run: AutomationRun, *, emit_event: bool) -> AutomationRun:
    update_run_status(
        db,
        run.organization_id,
        run,
        AutomationRunStatus.COMPLETED,
        finished_at=datetime.now(UTC),
    )
    if emit_event:
        _emit(
            db,
            run,
            AutomationRunEventType.COMPLETED,
            {"status": AutomationRunStatus.COMPLETED.value},
        )
    return run


def _build_context(
    db: DBSession,
    run: AutomationRun,
    event: AutomationEventContext,
    actor_id: uuid.UUID,
    action: AutomationAction,
    index: int,
    provider: LLMProvider | None,
) -> ActionContext:
    membership = get_membership(db, actor_id, run.organization_id)
    if membership is None:
        raise AutomationEngineError("actor_not_authorized")
    return ActionContext(
        db=db,
        organization_id=run.organization_id,
        actor_id=actor_id,
        actor_role=membership.role,
        run=run,
        application_id=event.application_id,
        event=event,
        action=action,
        index=index,
        action_id=derive_action_id(run_id=run.id, action=action, index=index),
        provider=provider,
    )


def execute_run(
    db: DBSession,
    run: AutomationRun,
    *,
    actor_id: uuid.UUID,
    provider: LLMProvider | None = None,
) -> AutomationRun:
    """Ejecuta una corrida pendiente; estados terminales devuelven la misma run."""
    if run.status is not AutomationRunStatus.PENDING:
        return run
    try:
        _require_actor(db, run.organization_id, actor_id)
    except AutomationEngineError as exc:
        return _fail_run(db, run, exc.code)

    version = get_version(db, run.organization_id, run.automation_id, run.version)
    if version is None:
        return _fail_run(db, run, "version_not_found")
    try:
        AutomationTrigger.model_validate(version.trigger)
        conditions = [
            AutomationCondition.model_validate(item) for item in version.conditions
        ]
        actions = [AutomationAction.model_validate(item) for item in version.actions]
        event = _load_event(db, run)
    except (ValidationError, AutomationEngineError, ValueError) as exc:
        code = exc.code if isinstance(exc, AutomationEngineError) else "invalid_snapshot"
        return _fail_run(db, run, code)
    update_run_status(
        db,
        run.organization_id,
        run,
        AutomationRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    try:
        evaluation = evaluate_conditions(conditions, event)
        _emit(
            db,
            run,
            AutomationRunEventType.CONDITION_EVALUATED,
            {
                "condition_count": len(conditions),
                "matched": evaluation.matched,
                "reason_code": evaluation.reason_code.value,
            },
        )
        if not evaluation.matched:
            if run.mode is AutomationRunMode.TEST:
                _emit(
                    db,
                    run,
                    AutomationRunEventType.DRY_RUN,
                    {"reason_code": evaluation.reason_code.value},
                )
            return _finish_completed(
                db, run, emit_event=run.mode is AutomationRunMode.LIVE
            )

        if run.mode is AutomationRunMode.TEST:
            _emit(
                db,
                run,
                AutomationRunEventType.DRY_RUN,
                {"reason_code": ConditionReasonCode.MATCHED.value},
            )
            for index, action in enumerate(actions):
                context = _build_context(db, run, event, actor_id, action, index, provider)
                planned = plan_action(context)
                _emit(
                    db,
                    run,
                    AutomationRunEventType.ACTION_PLANNED,
                    planned.event_payload,
                )
            return _finish_completed(db, run, emit_event=False)

        existing_approvals = list_approvals_for_run(
            db, run.organization_id, run.id, limit=_MAX_APPROVALS
        )
        approval_keys = {
            (approval.action_type.value, str(approval.payload.get("action_id")))
            for approval in existing_approvals
        }
        waiting = False
        for index, action in enumerate(actions):
            context = _build_context(db, run, event, actor_id, action, index, provider)
            action_key = (action.type.value, str(context.action_id))
            if get_run_event_by_action_id(db, run.organization_id, run.id, str(context.action_id)):
                continue
            if action_key in approval_keys:
                waiting = True
                continue
            result = _execute_with_retry(context)
            if result.status is ActionStatus.FAILED:
                return _fail_run(db, run, result.reason_code.value)
            if result.requires_approval:
                if len(approval_keys) >= _MAX_APPROVALS:
                    return _fail_run(db, run, "approval_limit_reached")
                approval = create_approval(
                    db,
                    organization_id=run.organization_id,
                    run_id=run.id,
                    action_type=action.type,
                    payload=result.event_payload,
                    created_by=actor_id,
                )
                approval_keys.add(action_key)
                payload = dict(result.event_payload)
                payload["approval_id"] = str(approval.id)
                _emit(db, run, AutomationRunEventType.APPROVAL_REQUESTED, payload)
                waiting = True
                continue
            _emit(db, run, AutomationRunEventType.ACTION_EXECUTED, result.event_payload)

        if waiting:
            update_run_status(
                db,
                run.organization_id,
                run,
                AutomationRunStatus.WAITING_APPROVAL,
            )
            return run
        return _finish_completed(db, run, emit_event=True)
    except AutomationEngineError as exc:
        return _fail_run(db, run, exc.code)
    except AutomationDomainError:
        return _fail_run(db, run, "invalid_snapshot")
    except Exception:
        log_structured(
            logging.WARNING,
            "automation.run_error",
            correlation_id=str(run.correlation_id),
            organization_id=str(run.organization_id),
        )
        return _fail_run(db, run, "action_failed")
