from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.agents.schemas import validate_safe_payload
from app.interviews.models import (
    InterviewFeedbackStatus,
    InterviewGuideStatus,
    InterviewQuestionCategory,
    InterviewQuestionStatus,
)

_EvidenceLine = Annotated[str, Field(min_length=1, max_length=500)]
_LimitationLine = Annotated[str, Field(min_length=1, max_length=200)]


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _ResponseModel(BaseModel):
    # Sin organization_id, CV ni rutas storage: el contrato público es acotado.
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class InterviewGuideCreate(_InputModel):
    """Alta de guía; tenant, autor y versión los fija el servicio."""

    application_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)


class InterviewGuideUpdate(_InputModel):
    """Edición acotada; el estado se valida contra el enum y sus transiciones."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: InterviewGuideStatus | None = None


class GuideRevisionCreate(_InputModel):
    """Snapshot saneado con el validador de payload seguro de agentes."""

    version: int = Field(ge=1)
    snapshot: dict[str, object]

    @field_validator("snapshot")
    @classmethod
    def _safe_snapshot(cls, value: dict[str, object]) -> dict[str, object]:
        return validate_safe_payload(value)


class InterviewQuestionCreate(_InputModel):
    """Pregunta ligada a un requisito del snapshot inmutable de la vacante."""

    requirement_id: uuid.UUID
    position: int = Field(ge=1)
    category: InterviewQuestionCategory
    question: str = Field(min_length=1, max_length=2000)
    evidence_focus: str = Field(min_length=1, max_length=1000)
    competency: str = Field(min_length=1, max_length=100)
    review_required: bool = False
    model_version: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=50)


class InterviewQuestionUpdate(_InputModel):
    """Edición, reordenación y revisión de una pregunta existente."""

    question: str | None = Field(default=None, min_length=1, max_length=2000)
    evidence_focus: str | None = Field(default=None, min_length=1, max_length=1000)
    competency: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=1)
    category: InterviewQuestionCategory | None = None
    status: InterviewQuestionStatus | None = None
    review_required: bool | None = None


class InterviewFeedbackCreate(_InputModel):
    """Registro humano; entrevistador y tenant los deriva el servicio."""

    question_id: uuid.UUID
    guide_id: uuid.UUID
    application_id: uuid.UUID


class InterviewFeedbackUpdate(_InputModel):
    """Evidencia observada, brechas y banderas; sin score ni decisión."""

    status: InterviewFeedbackStatus | None = None
    observed_evidence: list[_EvidenceLine] | None = Field(default=None, max_length=20)
    gaps: list[_EvidenceLine] | None = Field(default=None, max_length=20)
    follow_up_needed: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class _GenerationModel(BaseModel):
    """Contrato del proveedor: JSON estricto, sin claves dinámicas ni coerción."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)


class InterviewQuestionDraft(_GenerationModel):
    """Pregunta propuesta: ligada a un requisito y centrada en evidencia profesional."""

    requirement_id: uuid.UUID
    category: InterviewQuestionCategory = Field(strict=False)
    question: str = Field(min_length=10, max_length=2000)
    evidence_focus: str = Field(min_length=5, max_length=1000)
    competency: str = Field(min_length=2, max_length=100)
    limitations: list[_LimitationLine] = Field(default_factory=list, max_length=5)

    @field_validator("requirement_id", mode="before")
    @classmethod
    def _requirement_from_json(cls, value: object) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            return uuid.UUID(value)
        raise ValueError("requirement_id debe ser UUID")


class InterviewQuestionsOutput(_GenerationModel):
    """Salida del `interview_assistant`; sin score, decisión ni atributos protegidos."""

    questions: list[InterviewQuestionDraft] = Field(default_factory=list, max_length=20)
    model_version: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=50)
    limitations: list[_LimitationLine] = Field(default_factory=list, max_length=10)
    review_required: StrictBool = False

    @model_validator(mode="after")
    def _unique_requirement_category(self) -> InterviewQuestionsOutput:
        keys = [(item.requirement_id, item.category) for item in self.questions]
        if len(keys) != len(set(keys)):
            raise ValueError("Pregunta duplicada para requisito y categoría")
        return self


# --- Contratos HTTP: el tenant y los actores se derivan de la sesión. ---


class GenerateGuideRequest(_InputModel):
    """Solo la postulación; el resto lo fija el servicio autorizado."""

    application_id: uuid.UUID


class InterviewQuestionResult(_ResponseModel):
    """Pregunta trazable al requisito; sin CV, tenant ni storage."""

    id: uuid.UUID
    requirement_id: uuid.UUID
    category: InterviewQuestionCategory
    question: str
    evidence_focus: str
    competency: str
    status: InterviewQuestionStatus
    position: int
    review_required: bool
    model_version: str
    prompt_version: str


class InterviewGuideSummary(_ResponseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    title: str
    status: InterviewGuideStatus
    version: int
    created_at: datetime
    updated_at: datetime


class InterviewGuideDetail(InterviewGuideSummary):
    job_version_id: uuid.UUID | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    needs_review: bool = False
    questions: list[InterviewQuestionResult] = Field(default_factory=list)


class InterviewGuideListResponse(_ResponseModel):
    items: list[InterviewGuideSummary]
    total: int
    limit: int
    offset: int


class GuideGenerationResponse(_ResponseModel):
    guide_id: uuid.UUID
    application_id: uuid.UUID
    version: int
    status: InterviewGuideStatus
    model_version: str
    prompt_version: str
    job_version_id: uuid.UUID | None = None
    questions: list[InterviewQuestionResult] = Field(default_factory=list)
    rejected_questions: list[InterviewQuestionResult] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    needs_review: bool = False
    created: bool = False


class GuideRevisionResult(_ResponseModel):
    id: uuid.UUID
    version: int
    created_by: uuid.UUID
    created_at: datetime
    snapshot: dict[str, object]


class GuideRevisionListResponse(_ResponseModel):
    items: list[GuideRevisionResult]
    total: int
    limit: int
    offset: int


class InterviewQuestionCreateRequest(_InputModel):
    """Alta manual: política y requisito se revalidan en el servicio."""

    requirement_id: uuid.UUID
    position: int = Field(ge=1)
    category: InterviewQuestionCategory
    question: str = Field(min_length=10, max_length=2000)
    evidence_focus: str = Field(min_length=5, max_length=1000)
    competency: str = Field(min_length=2, max_length=100)
    review_required: bool = False


class InterviewQuestionUpdateRequest(_InputModel):
    """Edición acotada; el tenant, la versión y la auditoría los fija el servicio."""

    question: str | None = Field(default=None, min_length=10, max_length=2000)
    evidence_focus: str | None = Field(default=None, min_length=5, max_length=1000)
    competency: str | None = Field(default=None, min_length=2, max_length=100)
    position: int | None = Field(default=None, ge=1)
    status: InterviewQuestionStatus | None = None


class InterviewFeedbackSubmitRequest(_InputModel):
    """Observación humana; nunca incluye actor, score ni decisión."""

    observed_evidence: list[_EvidenceLine] = Field(default_factory=list, max_length=20)
    gaps: list[_EvidenceLine] = Field(default_factory=list, max_length=20)
    follow_up_needed: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class InterviewFeedbackResult(_ResponseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    requirement_id: uuid.UUID
    interviewer_id: uuid.UUID
    status: InterviewFeedbackStatus
    observed_evidence: list[str]
    gaps: list[str]
    follow_up_needed: bool
    notes: str | None
    submitted_at: datetime | None
    created_at: datetime


class InterviewFeedbackListResponse(_ResponseModel):
    items: list[InterviewFeedbackResult]
    total: int
    limit: int
    offset: int
