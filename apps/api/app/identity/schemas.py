from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.identity.models import MembershipRole, UserStatus
from app.identity.security import MAX_PASSWORD_BYTES


class _InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class RegisterRequest(_InputModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    # organization_name queda fuera: la creación de organizaciones es la unidad 3.

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError("La contraseña no puede superar 72 bytes.")
        return value


class LoginRequest(_InputModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    status: UserStatus


class MeResponse(UserResponse):
    # Contrato de la unidad 2: /auth/me no cambia en esta unidad.
    organizations: list[dict[str, str]] = Field(default_factory=list)


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(
        min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class MemberInvite(_InputModel):
    email: EmailStr
    role: MembershipRole


class MemberRoleUpdate(BaseModel):
    role: MembershipRole


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    name: str
    role: MembershipRole


class MessageResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str


class PasswordResetRequest(_InputModel):
    email: EmailStr


class PasswordResetConfirm(_InputModel):
    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError("La contraseña no puede superar 72 bytes.")
        return value


class PasswordResetRequestResponse(MessageResponse):
    # Demo sin SMTP: el token viaja solo en entornos no productivos.
    dev_token: str | None = None


class InvitationCreateResponse(MessageResponse):
    # Demo sin SMTP: el token viaja solo en entornos no productivos.
    dev_token: str | None = None


class InvitationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_name: str
    email: EmailStr
    role: MembershipRole
    expires_at: datetime


class InvitationAcceptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    organization_name: str
    role: MembershipRole
