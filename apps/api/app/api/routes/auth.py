from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DBSession

from app.core import config
from app.db.session import get_db
from app.identity.dependencies import get_current_user, verify_origin
from app.identity.models import User
from app.identity.schemas import (
    LoginRequest,
    MeResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegisterRequest,
    UserResponse,
)
from app.identity.service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    PasswordResetTokenError,
    authenticate_user,
    register_user,
    request_password_reset,
    revoke_session,
)
from app.identity.service import reset_password as reset_password_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DbDependency = Annotated[DBSession, Depends(get_db)]
OriginChecked = Annotated[None, Depends(verify_origin)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    _origin: OriginChecked,
    payload: RegisterRequest,
    db: DbDependency,
) -> User:
    try:
        return register_user(
            db, email=payload.email, password=payload.password, name=payload.name
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado."
        ) from None


@router.post("/login", response_model=UserResponse)
def login(
    _origin: OriginChecked,
    payload: LoginRequest,
    response: Response,
    db: DbDependency,
) -> User:
    settings = config.get_settings()
    try:
        user, token = authenticate_user(db, email=payload.email, password=payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas."
        ) from None

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production",
    )
    return user


@router.post("/forgot-password", response_model=PasswordResetRequestResponse)
def forgot_password(
    _origin: OriginChecked,
    payload: PasswordResetRequest,
    db: DbDependency,
) -> PasswordResetRequestResponse:
    settings = config.get_settings()
    token = request_password_reset(db, email=payload.email)
    return PasswordResetRequestResponse(
        message="Si el email existe, se generó una solicitud de recuperación.",
        dev_token=token if settings.APP_ENV != "production" else None,
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    _origin: OriginChecked,
    payload: PasswordResetConfirm,
    db: DbDependency,
) -> MessageResponse:
    try:
        reset_password_service(db, token=payload.token, password=payload.password)
    except PasswordResetTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace de recuperación no es válido o expiró.",
        ) from None
    return MessageResponse(message="Contraseña actualizada.")


@router.post("/logout", response_model=MessageResponse)
def logout(
    _origin: OriginChecked,
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: DbDependency,
) -> MessageResponse:
    settings = config.get_settings()
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        revoke_session(db, user=current_user, token=token)
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production",
    )
    return MessageResponse(message="Sesión cerrada.")


@router.get("/me", response_model=MeResponse)
def me(current_user: CurrentUser) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        status=current_user.status,
    )
