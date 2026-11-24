from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FieldName(StrEnum):
    """Únicos campos profesionales permitidos por la unidad 1."""

    NAME = "name"
    EMAIL = "email"
    LOCATION = "location"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    LANGUAGES = "languages"


class FieldStatus(StrEnum):
    """Subconjunto de estados de `ExtractedFieldStatus` que puede emitir el modelo."""

    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    MISSING = "missing"


class EvidenceRef(BaseModel):
    """Cita verificable contra el texto confirmado del documento.

    `offset` es relativo a la página, no al documento completo.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: uuid.UUID
    page: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=300)
    offset: int | None = Field(default=None, ge=0)


class ExtractedFieldPayload(BaseModel):
    """Un campo profesional; `value=None` solo es válido con `status=missing`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_name: FieldName
    value: str | list[str] | None = None
    status: FieldStatus
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class ExtractedProfile(BaseModel):
    """Salida estructurada del agente; sin atributos protegidos ni inferencias sensibles.

    `prompt_injection_detected` y su evidencia son señales de control del agente,
    no campos profesionales: la unidad 1 no define un `ExtractedField` para ellos.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_version: str = Field(min_length=1, max_length=50)
    fields: list[ExtractedFieldPayload] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    review_required: bool = False
    prompt_injection_detected: bool = False
    prompt_injection_evidence: list[EvidenceRef] = Field(
        default_factory=list, max_length=10
    )
