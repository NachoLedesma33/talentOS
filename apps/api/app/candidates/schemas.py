from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.candidates.models import CandidateProfileStatus


class _InputModel(BaseModel):
    # organization_id nunca entra por contrato: se deriva de la sesión autorizada.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CandidateCreate(_InputModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    location: str | None = Field(default=None, max_length=200)


class CandidateUpdate(_InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    location: str | None = Field(default=None, max_length=200)
    profile_status: CandidateProfileStatus | None = None


class CandidateResponse(_ResponseModel):
    id: uuid.UUID
    name: str
    email: str
    location: str | None
    profile_status: CandidateProfileStatus
    created_at: datetime
    updated_at: datetime


class NoteCreate(_InputModel):
    body: str = Field(min_length=1, max_length=2000)


class NoteResponse(_ResponseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime


class ActivityEntry(_ResponseModel):
    id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None
    resource_type: str
    resource_id: uuid.UUID
    timestamp: datetime


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int
    limit: int
    offset: int
