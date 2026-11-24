"""Evaluación determinista de condiciones sobre eventos de dominio saneados.

Sin LLM, sin SQL libre y sin texto libre como control: los únicos valores
comparables son enums del dominio (`ApplicationStage`, `JobStatus`).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.applications.models import ApplicationStage
from app.automation.models import AutomationTriggerEventType
from app.automation.schemas import (
    AutomationCondition,
    AutomationConditionField,
    AutomationConditionOperator,
)
from app.jobs.models import JobStatus

_MAX_CONDITIONS = 10


class ConditionReasonCode(StrEnum):
    """Códigos cerrados de evaluación; nunca texto libre del evento."""

    MATCHED = "matched"
    FIELD_MISSING = "field_missing"
    VALUE_MISMATCH = "value_mismatch"
    INVALID_EVENT_VALUE = "invalid_event_value"
    UNSUPPORTED_CONDITION = "unsupported_condition"


class ConditionResult(BaseModel):
    """Resultado acotado por condición: sin valores crudos del payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(max_length=40)
    operator: str = Field(max_length=10)
    matched: bool
    reason_code: ConditionReasonCode


class ConditionEvaluation(BaseModel):
    """Resultado agregado; todas las condiciones deben coincidir."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matched: bool
    results: list[ConditionResult] = Field(default_factory=list, max_length=_MAX_CONDITIONS)
    reason_code: ConditionReasonCode


class AutomationEventContext(BaseModel):
    """Payload normalizado del evento disparador, sin campos arbitrarios."""

    model_config = ConfigDict(
        extra="forbid", strict=True, str_strip_whitespace=True, frozen=True
    )

    event_type: AutomationTriggerEventType = Field(strict=False)
    application_id: uuid.UUID
    trigger_event_id: uuid.UUID
    correlation_id: uuid.UUID
    from_stage: str | None = None
    to_stage: str | None = None
    job_status: str | None = None

    @field_validator("application_id", "trigger_event_id", "correlation_id", mode="before")
    @classmethod
    def _uuid_from_json(cls, value: object) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            return uuid.UUID(value)
        raise ValueError("Identificador de evento inválido")

    @field_validator("from_stage", "to_stage", mode="before")
    @classmethod
    def _stage_from_enum(cls, value: object) -> object:
        if isinstance(value, ApplicationStage):
            return value.value
        return value

    @field_validator("job_status", mode="before")
    @classmethod
    def _status_from_enum(cls, value: object) -> object:
        if isinstance(value, JobStatus):
            return value.value
        return value

    @field_validator("from_stage", "to_stage")
    @classmethod
    def _valid_stage(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in {str(item.value) for item in ApplicationStage}:
            raise ValueError("Etapa de evento no permitida")
        return value

    @field_validator("job_status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in {str(item.value) for item in JobStatus}:
            raise ValueError("Estado de vacante no permitido")
        return value


def normalize_event_payload(payload: Mapping[str, object]) -> AutomationEventContext:
    """Convierte un payload persistido en el contexto cerrado que consume el motor."""
    return AutomationEventContext.model_validate(payload)


def _field_value(
    context: AutomationEventContext, field: AutomationConditionField
) -> str | None:
    if field is AutomationConditionField.TO_STAGE:
        return context.to_stage
    if field is AutomationConditionField.FROM_STAGE:
        return context.from_stage
    return context.job_status


def evaluate_condition(
    condition: AutomationCondition, context: AutomationEventContext
) -> ConditionResult:
    """Compara un valor enum contra el payload; campo ausente nunca coincide."""
    field = str(condition.field.value)
    operator = str(condition.operator.value)
    if condition.field not in set(AutomationConditionField):
        return ConditionResult(
            field=field[:40],
            operator=operator[:10],
            matched=False,
            reason_code=ConditionReasonCode.UNSUPPORTED_CONDITION,
        )
    actual = _field_value(context, condition.field)
    if actual is None:
        return ConditionResult(
            field=field,
            operator=operator,
            matched=False,
            reason_code=ConditionReasonCode.FIELD_MISSING,
        )
    expected = condition.value
    if isinstance(expected, str):
        if condition.operator is AutomationConditionOperator.EQ:
            matched = actual == expected
        elif condition.operator is AutomationConditionOperator.NEQ:
            matched = actual != expected
        else:
            matched = False
    elif condition.operator is AutomationConditionOperator.IN:
        matched = actual in expected
    else:
        matched = False
    reason = ConditionReasonCode.MATCHED if matched else ConditionReasonCode.VALUE_MISMATCH
    return ConditionResult(field=field, operator=operator, matched=matched, reason_code=reason)


def evaluate_conditions(
    conditions: Sequence[AutomationCondition], context: AutomationEventContext
) -> ConditionEvaluation:
    """Evalúa hasta diez condiciones; el resultado no expone valores del evento."""
    if len(conditions) > _MAX_CONDITIONS:
        return ConditionEvaluation(
            matched=False,
            results=[],
            reason_code=ConditionReasonCode.UNSUPPORTED_CONDITION,
        )
    results = [evaluate_condition(condition, context) for condition in conditions]
    failed = next((item for item in results if not item.matched), None)
    return ConditionEvaluation(
        matched=failed is None,
        results=results,
        reason_code=failed.reason_code if failed is not None else ConditionReasonCode.MATCHED,
    )
