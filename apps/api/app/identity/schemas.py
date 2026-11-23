from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.identity.models import UserStatus
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
    # La membresía se implementa en la unidad 3; hoy siempre se devuelve vacía.
    organizations: list[dict[str, str]] = Field(default_factory=list)


class MessageResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str
