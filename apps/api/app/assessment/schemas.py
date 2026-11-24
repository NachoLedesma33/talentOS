from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)


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
    review_required: bool
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


class RunAssessmentRequest(_InputModel):
    """Solo el ID de la postulación; el tenant se deriva de la sesión."""

    application_id: uuid.UUID


class StatusChange(_ResponseModel):
    before: RequirementEvaluationStatus | None
    after: RequirementEvaluationStatus | None
    changed: bool


class ExplanationChange(_ResponseModel):
    before: str | None
    after: str | None
    changed: bool


class EvidenceRefsChange(_ResponseModel):
    before: list[EvidenceRef]
    after: list[EvidenceRef]
    changed: bool


class ReviewRequiredChange(_ResponseModel):
    before: bool | None
    after: bool | None
    changed: bool


class RequirementComparison(_ResponseModel):
    """Cambios por requisito entre dos evaluaciones de la misma postulación."""

    requirement_id: uuid.UUID
    status: StatusChange
    explanation: ExplanationChange
    evidence_refs: EvidenceRefsChange
    review_required: ReviewRequiredChange


class ComparisonVersion(_ResponseModel):
    assessment_id: uuid.UUID
    status: AssessmentStatus
    model_version: str
    prompt_version: str


class AssessmentComparisonResult(_ResponseModel):
    """Comparación sin score: versiones y cambios trazables por requisito."""

    base: ComparisonVersion
    target: ComparisonVersion
    changes: list[RequirementComparison]


def assessment_result(
    assessment: Assessment,
    evaluations: Sequence[RequirementEvaluation] = (),
) -> AssessmentResult:
    """Construye el contrato público; nunca incluye CV, tenant ni rutas storage."""
    return AssessmentResult(
        id=assessment.id,
        application_id=assessment.application_id,
        job_version_id=assessment.job_version_id,
        candidate_id=assessment.candidate_id,
        status=assessment.status,
        model_version=assessment.model_version,
        prompt_version=assessment.prompt_version,
        summary=AssessmentSummary.model_validate(assessment.summary),
        limitations=list(assessment.limitations),
        evaluations=[RequirementEvaluationResult.model_validate(item) for item in evaluations],
        review_required=assessment.status is AssessmentStatus.NEEDS_REVIEW,
        created_at=assessment.created_at,
    )
