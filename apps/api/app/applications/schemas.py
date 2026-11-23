from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.applications.models import ApplicationSource, ApplicationStage


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApplicationCreate(_InputModel):
    job_id: uuid.UUID
    candidate_id: uuid.UUID
    source: ApplicationSource | None = None


class StageChangeRequest(_InputModel):
    to_stage: ApplicationStage
    note: str | None = Field(default=None, min_length=1, max_length=1000)


class ApplicationResponse(_ResponseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    candidate_id: uuid.UUID
    stage: ApplicationStage
    source: ApplicationSource | None
    created_at: datetime
    updated_at: datetime


class StageChangeResponse(_ResponseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    from_stage: ApplicationStage | None
    to_stage: ApplicationStage
    actor_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    limit: int
    offset: int
