from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.schemas import validate_safe_payload
from app.interviews.models import (
    InterviewFeedbackStatus,
    InterviewGuideStatus,
    InterviewQuestionCategory,
    InterviewQuestionStatus,
)

_EvidenceLine = Annotated[str, Field(min_length=1, max_length=500)]


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


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
