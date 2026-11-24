"""Contratos Pydantic del `job_analyst` (SDD 9.2.C y 9.3).

Salida estricta: sin score, ranking, decisión, atributos protegidos ni datos del
candidato. `requirement_id` es `null` cuando el requisito no existe en el snapshot
inmutable de la versión de vacante.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BoundedText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
ExplanationText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class JobAnalysisCategory(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    LANGUAGE = "language"
    CERTIFICATION = "certification"
    OTHER = "other"


class JobAnalysisImportance(StrEnum):
    REQUIRED = "required"
    DESIRABLE = "desirable"
    UNKNOWN = "unknown"


class JobAnalysisLevel(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    UNSPECIFIED = "unspecified"


class JobAnalysisSource(StrEnum):
    JOB_DESCRIPTION = "job_description"
    INFERRED_FROM_CONTEXT = "inferred_from_context"


class JobAnalysisAmbiguityKind(StrEnum):
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
    MISSING = "missing"


class JobAnalysisRequirement(BaseModel):
    """Requisito interpretable, vinculado opcionalmente al snapshot inmutable."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    requirement_id: uuid.UUID | None = Field(default=None, strict=False)
    description: ExplanationText
    category: JobAnalysisCategory = Field(strict=False)
    evidence_focus: ExplanationText
    importance: JobAnalysisImportance = Field(strict=False)
    level: JobAnalysisLevel = Field(strict=False)
    source: JobAnalysisSource = Field(strict=False)
    limitations: list[BoundedText] = Field(default_factory=list, max_length=10)


class JobAnalysisAmbiguity(BaseModel):
    """Ambigüedad, contradicción o dato ausente; nunca una decisión."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: JobAnalysisAmbiguityKind = Field(strict=False)
    description: ExplanationText
    related_requirement_id: uuid.UUID | None = Field(default=None, strict=False)
    limitations: list[BoundedText] = Field(default_factory=list, max_length=10)


class JobAnalysisCriterion(BaseModel):
    """Criterio medible propuesto para revisión humana; sin peso ni puntuación."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    related_requirement_id: uuid.UUID | None = Field(default=None, strict=False)
    description: ExplanationText
    evidence_focus: ExplanationText
    limitations: list[BoundedText] = Field(default_factory=list, max_length=10)


class JobAnalysisOutput(BaseModel):
    """Contrato estructurado del `job_analyst`; validado antes de devolverse."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    requirements: list[JobAnalysisRequirement] = Field(min_length=1, max_length=20)
    ambiguities: list[JobAnalysisAmbiguity] = Field(default_factory=list, max_length=10)
    proposed_criteria: list[JobAnalysisCriterion] = Field(default_factory=list, max_length=10)
    limitations: list[BoundedText] = Field(default_factory=list, max_length=10)
    review_required: bool
    model_version: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=50)
