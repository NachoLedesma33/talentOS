from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.assessment.models import AssessmentStatus, RequirementEvaluationStatus


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class EvidenceRef(_InputModel):
    """Cita verificable; el dominio comprueba que exista en el texto confirmado."""

    document_id: uuid.UUID
    field_name: str = Field(min_length=1, max_length=100)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)
    offset: int | None = Field(default=None, ge=0)


class RequirementEvaluationCreate(_InputModel):
    requirement_id: uuid.UUID
    status: RequirementEvaluationStatus
    explanation: str = Field(min_length=1, max_length=2000)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False


class RequirementEvaluationResult(_ResponseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    status: RequirementEvaluationStatus
    explanation: str
    evidence: list[EvidenceRef]
    limitations: list[str]
    review_required: bool
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class AssessmentSummary(_InputModel):
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class AssessmentResult(_ResponseModel):
    """Evaluación explicable; sin score, sin organization_id y sin atributos protegidos."""

    id: uuid.UUID
    application_id: uuid.UUID
    job_version_id: uuid.UUID
    candidate_id: uuid.UUID
    status: AssessmentStatus
    model_version: str
    prompt_version: str
    summary: AssessmentSummary
    limitations: list[str]
    evaluations: list[RequirementEvaluationResult] = Field(default_factory=list)
    created_at: datetime


class AssessmentListResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    items: list[AssessmentResult]
    total: int
    limit: int
    offset: int


class ReviewDecision(_InputModel):
    """Corrección humana: estado explícito y explicación opcional."""

    status: RequirementEvaluationStatus
    explanation: str | None = Field(default=None, max_length=2000)
