from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.jobs.models import JobStatus, RequirementCategory, RequirementImportance


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobCreate(_InputModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    modality: str | None = None
    location: str | None = None
    seniority: str | None = None
    owner_id: uuid.UUID


class JobUpdate(_InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    modality: str | None = None
    location: str | None = None
    seniority: str | None = None
    owner_id: uuid.UUID | None = None


class JobStatusUpdate(_InputModel):
    status: JobStatus


class RequirementCreate(_InputModel):
    category: RequirementCategory
    description: str = Field(min_length=1)
    importance: RequirementImportance
    expected_level: str | None = None
    acceptable_evidence: list[str] = Field(default_factory=list)
    weight: float = Field(default=0.0, ge=0.0, le=1.0)
    weight_justification: str = ""

    @model_validator(mode="after")
    def justify_positive_weight(self) -> RequirementCreate:
        if self.weight > 0 and not self.weight_justification:
            raise ValueError("weight > 0 requiere weight_justification")
        return self


class RequirementUpdate(_InputModel):
    category: RequirementCategory | None = None
    description: str | None = Field(default=None, min_length=1)
    importance: RequirementImportance | None = None
    expected_level: str | None = None
    acceptable_evidence: list[str] | None = None
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_justification: str | None = None

    @model_validator(mode="after")
    def justify_positive_weight(self) -> RequirementUpdate:
        if self.weight is not None and self.weight > 0 and not self.weight_justification:
            raise ValueError("weight > 0 requiere weight_justification")
        return self


class JobResponse(_ResponseModel):
    id: uuid.UUID
    title: str
    description: str
    status: JobStatus
    modality: str | None
    location: str | None
    seniority: str | None
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RequirementResponse(_ResponseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    category: RequirementCategory
    description: str
    importance: RequirementImportance
    expected_level: str | None
    acceptable_evidence: list[str]
    weight: float
    weight_justification: str
    created_at: datetime
    updated_at: datetime


class JobVersionResponse(_ResponseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    version: int
    snapshot: dict[str, object]
    created_at: datetime


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int
