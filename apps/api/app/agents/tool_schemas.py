"""Contratos Pydantic de las tools acotadas del runtime (SDD §10).

Los datos del candidato entran como contenido no confiable: aquí solo se
estructuran campos permitidos, citas truncadas y salidas verificables. Ningún
contrato acepta campos libres, CV completo ni instrucciones para el agente.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.models import ApprovalStatus
from app.applications.models import ApplicationStage
from app.assessment.matching_schema import AssessmentOutput
from app.assessment.models import RequirementEvaluationStatus
from app.candidates.models import CandidateProfileStatus
from app.documents.models import ExtractedFieldName


class _StrictToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


class GetJobRequirementsInput(_StrictToolModel):
    """Versión inmutable de la vacante; `job_version_id` es el UUID de la fila."""

    job_id: uuid.UUID
    job_version_id: uuid.UUID | None = None


class GetCandidateProfileInput(_StrictToolModel):
    candidate_id: uuid.UUID


class GetConfirmedDocumentTextInput(_StrictToolModel):
    document_id: uuid.UUID
    field_name: ExtractedFieldName | None = None
    limit: int = Field(default=5, ge=1, le=20, strict=True)


class CreateAssessmentDraftInput(_StrictToolModel):
    application_id: uuid.UUID
    result: AssessmentOutput


class MessageTemplate(StrEnum):
    INITIAL_CONTACT = "initial_contact"
    INTERVIEW_INVITE = "interview_invite"
    FOLLOW_UP = "follow_up"


class MessageTemplateData(_StrictToolModel):
    """Datos acotados para renderizar un borrador; sin nombre ni email del candidato."""

    template: MessageTemplate
    topic: str = Field(min_length=1, max_length=120)
    language: Literal["es", "en"] = "es"
    call_to_action: str = Field(min_length=1, max_length=120)


class CreateMessageDraftInput(_StrictToolModel):
    candidate_id: uuid.UUID
    template_data: MessageTemplateData


class ApprovalActionType(StrEnum):
    CREATE_ASSESSMENT = "create_assessment"
    SEND_MESSAGE = "send_message"
    CHANGE_STAGE = "change_stage"


class CreateAssessmentApprovalPayload(_StrictToolModel):
    action_type: Literal[ApprovalActionType.CREATE_ASSESSMENT]
    application_id: uuid.UUID
    assessment_draft_id: uuid.UUID
    review_required: bool


class SendMessageApprovalPayload(_StrictToolModel):
    action_type: Literal[ApprovalActionType.SEND_MESSAGE]
    candidate_id: uuid.UUID
    message_draft_id: uuid.UUID
    template: MessageTemplate


class ChangeStageApprovalPayload(_StrictToolModel):
    action_type: Literal[ApprovalActionType.CHANGE_STAGE]
    application_id: uuid.UUID
    from_stage: ApplicationStage
    to_stage: ApplicationStage
    reason: str = Field(min_length=1, max_length=300)


ApprovalPayload = Annotated[
    CreateAssessmentApprovalPayload
    | SendMessageApprovalPayload
    | ChangeStageApprovalPayload,
    Field(discriminator="action_type"),
]


class RequestHumanApprovalInput(_StrictToolModel):
    """Solicitud humana: el tipo cierra la forma del payload permitido."""

    action_type: ApprovalActionType
    payload: ApprovalPayload

    @model_validator(mode="after")
    def _action_matches_payload(self) -> RequestHumanApprovalInput:
        if self.payload.action_type != self.action_type:
            raise ValueError("action_type no coincide con payload")
        return self


# ---------------------------------------------------------------------------
# Salidas
# ---------------------------------------------------------------------------


class JobRequirementItem(_StrictToolModel):
    requirement_id: uuid.UUID
    description: str = Field(max_length=1000)
    category: str = Field(max_length=50)
    importance: str = Field(max_length=50)
    expected_level: str | None = Field(default=None, max_length=100)


class JobRequirementsResult(_StrictToolModel):
    job_id: uuid.UUID
    job_version_id: uuid.UUID
    version: int = Field(ge=1)
    requirements: list[JobRequirementItem] = Field(default_factory=list, max_length=20)
    missing: list[str] = Field(default_factory=list, max_length=10)


class ConfirmedQuote(_StrictToolModel):
    document_id: uuid.UUID
    field_name: ExtractedFieldName
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=400)
    offset: int | None = Field(default=None, ge=0)


class ConfirmedField(_StrictToolModel):
    field_name: ExtractedFieldName
    value: str = Field(max_length=500)
    document_id: uuid.UUID
    status: Literal["confirmed", "corrected"]


class CandidateProfileResult(_StrictToolModel):
    candidate_id: uuid.UUID
    profile_status: CandidateProfileStatus
    fields: list[ConfirmedField] = Field(default_factory=list, max_length=20)
    evidence: list[ConfirmedQuote] = Field(default_factory=list, max_length=20)
    missing: list[str] = Field(default_factory=list, max_length=10)


class ConfirmedDocumentTextResult(_StrictToolModel):
    document_id: uuid.UUID
    field_name: ExtractedFieldName | None = None
    quotes: list[ConfirmedQuote] = Field(default_factory=list, max_length=20)
    missing: list[str] = Field(default_factory=list, max_length=10)


class StatusCount(_StrictToolModel):
    status: RequirementEvaluationStatus
    count: int = Field(ge=0)


class AssessmentDraftResult(_StrictToolModel):
    draft_id: uuid.UUID
    application_id: uuid.UUID
    statuses_summary: list[StatusCount] = Field(default_factory=list, max_length=4)
    review_required: bool
    model_version: str = Field(max_length=100)
    prompt_version: str = Field(max_length=50)


class MessageDraftResult(_StrictToolModel):
    draft_id: uuid.UUID
    candidate_id: uuid.UUID
    template: MessageTemplate
    language: Literal["es", "en"]
    text: str = Field(min_length=1, max_length=500)
    char_count: int = Field(ge=1)


class ApprovalRequestResult(_StrictToolModel):
    approval_id: uuid.UUID
    action_type: ApprovalActionType
    status: ApprovalStatus
    requested_by: uuid.UUID
    requested_at: datetime
    agent_run_id: uuid.UUID
