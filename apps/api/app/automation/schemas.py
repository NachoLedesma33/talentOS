from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.agents.schemas import validate_safe_payload
from app.applications.models import ApplicationStage
from app.automation.models import (
    AutomationActionType,
    AutomationApprovalStatus,
    AutomationRunEventType,
    AutomationRunMode,
    AutomationRunStatus,
    AutomationStatus,
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


# --- Contratos HTTP -------------------------------------------------------
# El tenant nunca entra por body. Las respuestas solo exponen IDs, enums y
# metadatos verificables: sin CV, PII, secretos ni rutas de storage.


class AutomationCreateRequest(_StrictModel):
    """Alta de una regla en `draft`; la configuración se envía por versión."""

    name: str = Field(min_length=1, max_length=200)


class AutomationStatusUpdate(_StrictModel):
    """Transición permitida por el modelo; strings arbitrarios se rechazan."""

    status: AutomationStatus = Field(strict=False)


class AutomationExecutionRequest(_StrictModel):
    """Disparo manual sobre una postulación del tenant autenticado."""

    application_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=_KEY_PATTERN)
    correlation_id: uuid.UUID | None = None

    @field_validator("application_id", "correlation_id", mode="before")
    @classmethod
    def _uuid_from_json(cls, value: object, info: ValidationInfo) -> uuid.UUID | None:
        if value is None and info.field_name == "correlation_id":
            return None
        return cls._uuid(value, str(info.field_name))


class AutomationDecisionRequest(_StrictModel):
    """Decisión humana; `note` no se persiste ni se registra en logs."""

    decision: str = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, min_length=1, max_length=500)


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AutomationSnapshot(_ResponseModel):
    trigger: dict[str, object]
    conditions: list[dict[str, object]]
    actions: list[dict[str, object]]
    created_at: datetime | None = None


class AutomationSummary(_ResponseModel):
    id: uuid.UUID
    name: str
    status: AutomationStatus
    current_version: int
    created_at: datetime
    updated_at: datetime


class AutomationDetail(AutomationSummary):
    active_version: AutomationSnapshot | None = None


class AutomationVersionResult(_ResponseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    version: int
    created_at: datetime


class AutomationListResponse(_ResponseModel):
    items: list[AutomationSummary]
    total: int
    limit: int
    offset: int


class AutomationEventCount(_ResponseModel):
    event_type: AutomationRunEventType
    count: int


class AutomationTestResult(_ResponseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    status: AutomationRunStatus
    mode: AutomationRunMode
    correlation_id: uuid.UUID
    event_summary: list[AutomationEventCount]


class RunSummary(_ResponseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    version: int
    mode: AutomationRunMode
    status: AutomationRunStatus
    correlation_id: uuid.UUID
    trigger_event_type: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class RunDetail(RunSummary):
    started_at: datetime | None
    finished_at: datetime | None
    draft_ids: list[uuid.UUID] = Field(default_factory=list)
    approval_ids: list[uuid.UUID] = Field(default_factory=list)


class RunListResponse(_ResponseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class RunEventItem(_ResponseModel):
    event_type: AutomationRunEventType
    created_at: datetime
    correlation_id: uuid.UUID
    payload: dict[str, object]


class RunEventListResponse(_ResponseModel):
    items: list[RunEventItem]
    total: int
    limit: int
    offset: int


class ApprovalItem(_ResponseModel):
    id: uuid.UUID
    action_type: AutomationActionType
    status: AutomationApprovalStatus
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecisionResult(_ResponseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    action_type: AutomationActionType
    status: AutomationApprovalStatus
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    run_status: AutomationRunStatus


class RunQueueResult(_ResponseModel):
    id: uuid.UUID
    status: AutomationRunStatus
    queued: bool
    correlation_id: uuid.UUID
