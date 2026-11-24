"""Manejadores cerrados de acciones del motor de automatización.

Ningún manejador envía correo, ejecuta shell, toca filesystem ni escribe SQL
libre. Las notas se reducen a hashes: no se persiste texto de candidato.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as DBSession

from app.agents.schemas import validate_safe_payload
from app.applications.models import ApplicationStage
from app.automation.conditions import AutomationEventContext
from app.automation.models import (
    AutomationActionType,
    AutomationApproval,
    AutomationRun,
)
from app.automation.schemas import AutomationAction
from app.identity.models import MembershipRole
from app.llm.provider import LLMProvider


class ActionStatus(StrEnum):
    PLANNED = "planned"
    EXECUTED = "executed"
    APPROVAL_REQUIRED = "approval_required"
    FAILED = "failed"


class ActionReasonCode(StrEnum):
    PLANNED = "planned"
    EXECUTED = "executed"
    APPROVAL_REQUIRED = "approval_required"
    UNSUPPORTED_ACTION = "unsupported_action"
    INVALID_CONTEXT = "invalid_context"
    TARGET_STAGE_REQUIRED = "target_stage_required"
    INVALID_APPROVAL_PAYLOAD = "invalid_approval_payload"
    ACTION_TIMEOUT = "action_timeout"
    ACTION_FAILED = "action_failed"
    PROVIDER_FAILED = "provider_failed"


class ActionResult(BaseModel):
    """Resultado acotado; `event_payload` es el único contenido persistible."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: AutomationActionType = Field(strict=False)
    status: ActionStatus
    resource_id: uuid.UUID | None = None
    reason_code: ActionReasonCode
    requires_approval: bool = False
    event_payload: dict[str, object] = Field(default_factory=dict)


class AppliedEffect(BaseModel):
    """Efecto aplicado tras una decisión humana; sin decisión automática."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    applied: bool
    resource_id: uuid.UUID | None = None
    reason_code: ActionReasonCode


@dataclass(frozen=True)
class ActionContext:
    """Contexto validado por el servicio/engine antes de invocar un manejador."""

    db: DBSession
    organization_id: uuid.UUID
    actor_id: uuid.UUID
    actor_role: MembershipRole
    run: AutomationRun
    application_id: uuid.UUID
    event: AutomationEventContext
    action: AutomationAction
    index: int
    action_id: uuid.UUID
    provider: LLMProvider | None = None

    def __post_init__(self) -> None:
        if self.run.organization_id != self.organization_id:
            raise ValueError("invalid_context")
        if self.event.application_id != self.application_id:
            raise ValueError("invalid_context")
        if self.actor_role not in {
            MembershipRole.OWNER,
            MembershipRole.ADMIN,
            MembershipRole.RECRUITER,
        }:
            raise ValueError("invalid_context")
        if self.index < 0:
            raise ValueError("invalid_context")
        if self.action_id != derive_action_id(
            run_id=self.run.id,
            action=self.action,
            index=self.index,
        ):
            raise ValueError("invalid_context")
        validate_safe_payload(self.action.model_dump(mode="json"))


def derive_action_id(
    *, run_id: uuid.UUID, action: AutomationAction, index: int
) -> uuid.UUID:
    """ID estable derivado de `(run_id, acción, índice, payload saneado)`."""
    canonical = json.dumps(
        validate_safe_payload(cast(dict[str, object], action.model_dump(mode="json"))),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"automation|{run_id}|{action.type.value}|{index}|{digest}"
    )


def _hash_text(value: str | None) -> str | None:
    """Hash de texto saneado: la nota nunca viaja en eventos ni aprobaciones."""
    if value is None:
        return None
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def _base_payload(context: ActionContext, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "organization_id": str(context.organization_id),
        "run_id": str(context.run.id),
        "correlation_id": str(context.event.correlation_id),
        "application_id": str(context.application_id),
        "trigger_event_id": str(context.event.trigger_event_id),
        "action_id": str(context.action_id),
        "action_type": context.action.type.value,
        "resource_id": str(context.action_id),
        "action_index": context.index,
    }
    payload.update(extra)
    return validate_safe_payload(payload)


def _note_fields(context: ActionContext) -> dict[str, object]:
    note = context.action.payload.note
    return {
        "template_id": context.action.payload.template_id,
        "note_hash": _hash_text(note),
        "note_length": len(note.strip()) if note is not None else 0,
    }


def _create_task(context: ActionContext) -> ActionResult:
    payload = _base_payload(context, kind="task", **_note_fields(context))
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.EXECUTED,
        resource_id=context.action_id,
        reason_code=ActionReasonCode.EXECUTED,
        event_payload=payload,
    )


def _record_note(context: ActionContext) -> ActionResult:
    payload = _base_payload(context, kind="note", **_note_fields(context))
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.EXECUTED,
        resource_id=context.action_id,
        reason_code=ActionReasonCode.EXECUTED,
        event_payload=payload,
    )


def _create_message_draft(context: ActionContext) -> ActionResult:
    # Borrador acotado: sin direcciones, CV ni canal de envío.
    payload = _base_payload(
        context,
        kind="message_draft",
        draft_id=str(context.action_id),
        template_id=context.action.payload.template_id,
        to_stage=context.event.to_stage,
    )
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.APPROVAL_REQUIRED,
        resource_id=context.action_id,
        reason_code=ActionReasonCode.APPROVAL_REQUIRED,
        requires_approval=True,
        event_payload=payload,
    )


def _request_approval(context: ActionContext) -> ActionResult:
    payload = _base_payload(context, kind="approval_request", **_note_fields(context))
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.APPROVAL_REQUIRED,
        resource_id=context.action_id,
        reason_code=ActionReasonCode.APPROVAL_REQUIRED,
        requires_approval=True,
        event_payload=payload,
    )


def _propose_stage_change(context: ActionContext) -> ActionResult:
    target = context.action.payload.target_stage
    if target is None:
        return ActionResult(
            type=context.action.type,
            status=ActionStatus.FAILED,
            reason_code=ActionReasonCode.TARGET_STAGE_REQUIRED,
            event_payload=_base_payload(context, kind="stage_change_proposal"),
        )
    payload = _base_payload(
        context,
        kind="stage_change_proposal",
        target_stage=target.value,
        from_stage=context.event.from_stage,
        **_note_fields(context),
    )
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.APPROVAL_REQUIRED,
        resource_id=context.action_id,
        reason_code=ActionReasonCode.APPROVAL_REQUIRED,
        requires_approval=True,
        event_payload=payload,
    )


def _run_authorized_analysis(context: ActionContext) -> ActionResult:
    """Delega en assessment con el actor autorizado; sin decisiones automáticas."""
    import app.assessment.service as assessment_service

    if context.provider is None:
        assessment = assessment_service.run_assessment(
            context.db,
            organization_id=context.organization_id,
            application_id=context.application_id,
            actor_id=context.actor_id,
        )
    else:
        with patch.object(
            assessment_service, "get_llm_provider", return_value=context.provider
        ):
            assessment = assessment_service.run_assessment(
                context.db,
                organization_id=context.organization_id,
                application_id=context.application_id,
                actor_id=context.actor_id,
            )
    payload = _base_payload(context, kind="authorized_analysis")
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.EXECUTED,
        resource_id=assessment.id,
        reason_code=ActionReasonCode.EXECUTED,
        event_payload=payload,
    )


_HANDLERS: dict[AutomationActionType, Callable[[ActionContext], ActionResult]] = {
    AutomationActionType.CREATE_TASK: _create_task,
    AutomationActionType.RECORD_NOTE: _record_note,
    AutomationActionType.CREATE_MESSAGE_DRAFT: _create_message_draft,
    AutomationActionType.REQUEST_APPROVAL: _request_approval,
    AutomationActionType.PROPOSE_STAGE_CHANGE: _propose_stage_change,
    AutomationActionType.RUN_AUTHORIZED_ANALYSIS: _run_authorized_analysis,
}


def plan_action(context: ActionContext) -> ActionResult:
    """Modo prueba: ni escrituras de dominio ni proveedor, solo traza."""
    payload = _base_payload(context, kind="planned")
    return ActionResult(
        type=context.action.type,
        status=ActionStatus.PLANNED,
        resource_id=context.action_id,
        reason_code=ActionReasonCode.PLANNED,
        event_payload=payload,
    )


def execute_action(context: ActionContext) -> ActionResult:
    handler = _HANDLERS.get(context.action.type)
    if handler is None:
        return ActionResult(
            type=context.action.type,
            status=ActionStatus.FAILED,
            reason_code=ActionReasonCode.UNSUPPORTED_ACTION,
            event_payload=_base_payload(context, kind="unsupported"),
        )
    return handler(context)


def apply_approved_action(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    run: AutomationRun,
    approval: AutomationApproval,
    actor_id: uuid.UUID,
) -> AppliedEffect:
    """Aplica solo el efecto cuya aprobación ya fue decidida por una persona."""
    if approval.action_type is not AutomationActionType.PROPOSE_STAGE_CHANGE:
        return AppliedEffect(applied=True, reason_code=ActionReasonCode.EXECUTED)

    raw_target = approval.payload.get("target_stage")
    raw_application = approval.payload.get("application_id")
    if not isinstance(raw_target, str) or not isinstance(raw_application, str):
        return AppliedEffect(
            applied=False, reason_code=ActionReasonCode.INVALID_APPROVAL_PAYLOAD
        )
    try:
        target = ApplicationStage(raw_target)
        application_id = uuid.UUID(raw_application)
    except ValueError:
        return AppliedEffect(
            applied=False, reason_code=ActionReasonCode.INVALID_APPROVAL_PAYLOAD
        )

    from app.applications import service as application_service

    change = application_service.change_stage(
        db,
        organization_id=organization_id,
        application_id=application_id,
        to_stage=target,
        actor_id=actor_id,
        automation_run_id=run.id,
        dispatch_event=False,
    )
    return AppliedEffect(
        applied=True, resource_id=change.id, reason_code=ActionReasonCode.EXECUTED
    )
