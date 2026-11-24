from __future__ import annotations

import re
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.agents.schemas import validate_safe_payload
from app.applications.models import ApplicationStage
from app.automation.models import (
    AutomationActionType,
    AutomationApprovalStatus,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationTriggerEventType,
)
from app.jobs.models import JobStatus

_CONTACT_PATTERN = re.compile(r"(?i)(@|https?://|www\.|\b\d{7,}\b)")
_KEY_PATTERN = r"^[A-Za-z0-9_.:-]+$"
_MAX_CONDITIONS = 10
_MAX_ACTIONS = 10
_MAX_VALUES = 8


class AutomationConditionField(StrEnum):
    TO_STAGE = "to_stage"
    FROM_STAGE = "from_stage"
    JOB_STATUS = "job_status"


class AutomationConditionOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    IN = "in"


class _StrictModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)

    @staticmethod
    def _uuid(value: object, field: str) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            return uuid.UUID(value)
        raise ValueError(f"{field} debe ser UUID")


class AutomationTrigger(_StrictModel):
    """Disparo cerrado del MVP: solo cambio de etapa de postulación."""

    event_type: AutomationTriggerEventType = Field(strict=False)

    @field_validator("event_type")
    @classmethod
    def _single_domain_event(cls, value: AutomationTriggerEventType) -> AutomationTriggerEventType:
        if value is not AutomationTriggerEventType.APPLICATION_STAGE_CHANGED:
            raise ValueError("Evento de automatización no soportado")
        return value


class AutomationCondition(_StrictModel):
    """Condición determinista sobre enums conocidos; sin comparaciones arbitrarias."""

    field: AutomationConditionField = Field(strict=False)
    operator: AutomationConditionOperator = Field(strict=False)
    value: str | list[str] = Field(min_length=1, max_length=100)

    @field_validator("value")
    @classmethod
    def _valid_value(
        cls, value: str | list[str], info: ValidationInfo
    ) -> str | list[str]:
        raw_field = info.data.get("field")
        raw_operator = info.data.get("operator")
        if isinstance(value, list):
            if raw_operator is not AutomationConditionOperator.IN:
                raise ValueError("operator=in es obligatorio para una lista")
            if not 1 <= len(value) <= _MAX_VALUES:
                raise ValueError("Lista de valores fuera de límites")
            items = value
        else:
            if raw_operator is AutomationConditionOperator.IN:
                raise ValueError("operator=in requiere una lista")
            items = [value]
        if raw_field in (
            AutomationConditionField.TO_STAGE,
            AutomationConditionField.FROM_STAGE,
        ):
            allowed = {str(item.value) for item in ApplicationStage}
        elif raw_field is AutomationConditionField.JOB_STATUS:
            allowed = {str(item.value) for item in JobStatus}
        else:
            raise ValueError("Campo de condición no soportado")
        if any(item not in allowed for item in items):
            raise ValueError("Valor de condición fuera del enum permitido")
        return value


class AutomationActionPayload(_StrictModel):
    """Borradores y referencias acotadas; sin correos, direcciones ni PII."""

    template_id: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=_KEY_PATTERN
    )
    note: str | None = Field(default=None, min_length=1, max_length=1000)
    target_stage: ApplicationStage | None = Field(default=None, strict=False)

    @field_validator("note")
    @classmethod
    def _note_without_contact(cls, value: str | None) -> str | None:
        if value is not None and _CONTACT_PATTERN.search(value):
            raise ValueError("La nota no puede incluir correos, URLs ni datos de contacto")
        return value


class AutomationAction(_StrictModel):
    """Acción permitida; el motor no ejecuta efectos externos en el MVP."""

    type: AutomationActionType = Field(strict=False)
    payload: AutomationActionPayload = Field(default_factory=AutomationActionPayload)

    @model_validator(mode="after")
    def _safe_payload(self) -> AutomationAction:
        validate_safe_payload(self.model_dump(mode="json"))
        return self


class AutomationVersionCreate(_StrictModel):
    """Snapshot completo y saneado de la configuración de una automatización."""

    trigger: AutomationTrigger
    conditions: list[AutomationCondition] = Field(
        default_factory=list, max_length=_MAX_CONDITIONS
    )
    actions: list[AutomationAction] = Field(min_length=1, max_length=_MAX_ACTIONS)

    @model_validator(mode="after")
    def _safe_snapshot(self) -> AutomationVersionCreate:
        self.to_snapshot()
        return self

    def to_snapshot(self) -> dict[str, object]:
        """Representación JSON-compatible validada antes de persistirse."""
        snapshot: dict[str, object] = {
            "trigger": self.trigger.model_dump(mode="json"),
            "conditions": [item.model_dump(mode="json") for item in self.conditions],
            "actions": [item.model_dump(mode="json") for item in self.actions],
        }
        return validate_safe_payload(snapshot)


class AutomationRunCreate(_StrictModel):
    """Alta de ejecución; tenant y actor los deriva el servicio autorizado."""

    automation_id: uuid.UUID
    version: int = Field(ge=1)
    mode: AutomationRunMode = Field(strict=False)
    trigger_event_type: AutomationTriggerEventType = Field(strict=False)
    trigger_event_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=_KEY_PATTERN)
    correlation_id: uuid.UUID

    @field_validator("automation_id", "trigger_event_id", "correlation_id", mode="before")
    @classmethod
    def _uuid_from_json(cls, value: object, info: ValidationInfo) -> uuid.UUID:
        return cls._uuid(value, str(info.field_name))


class AutomationRunEventCreate(_StrictModel):
    """Traza saneada: la clave de idempotencia se mantiene fuera del payload."""

    event_type: AutomationRunEventType = Field(strict=False)
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _safe_payload(cls, value: dict[str, object]) -> dict[str, object]:
        return validate_safe_payload(value)


class AutomationApprovalDecision(_StrictModel):
    """Decisión humana; el aprobador se deriva de la sesión, nunca del body."""

    approval_id: uuid.UUID
    decision: AutomationApprovalStatus = Field(strict=False)

    @field_validator("approval_id", mode="before")
    @classmethod
    def _uuid_from_json(cls, value: object) -> uuid.UUID:
        return cls._uuid(value, "approval_id")

    @field_validator("decision")
    @classmethod
    def _only_decided_values(
        cls, value: AutomationApprovalStatus
    ) -> AutomationApprovalStatus:
        if value is AutomationApprovalStatus.PENDING:
            raise ValueError("La decisión no puede quedar pendiente")
        return value
