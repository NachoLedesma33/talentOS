from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.assessment.models import RequirementEvaluationStatus


class MatchingEvidenceRef(BaseModel):
    """Cita acotada contra un campo confirmado del candidato; se verifica en el dominio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: uuid.UUID
    field_name: str = Field(min_length=1, max_length=100)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=300)
    offset: int | None = Field(default=None, ge=0)


class MatchingResult(BaseModel):
    """Salida por requisito (SDD 9.5): hechos, limitaciones y revisión; sin score."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: uuid.UUID
    status: RequirementEvaluationStatus
    evidence_refs: list[MatchingEvidenceRef] = Field(
        default_factory=list, max_length=10
    )
    explanation: str = Field(min_length=1, max_length=2000)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    review_required: bool = False


class AssessmentOutput(BaseModel):
    """Contrato estructurado del `matching_analyst`; sin atributos protegidos ni ranking."""

    model_config = ConfigDict(extra="forbid")

    evaluations: list[MatchingResult] = Field(default_factory=list, max_length=20)
    strengths: list[str] = Field(default_factory=list, max_length=10)
    gaps: list[str] = Field(default_factory=list, max_length=10)
    questions: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    review_required: bool = False
    model_version: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=50)
