from __future__ import annotations

import logging
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from time import monotonic

import email_validator
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    agents,
    analytics,
    applications,
    assessment,
    auth,
    automation,
    candidates,
    documents,
    health,
    integrations,
    interviews,
    jobs,
    organizations,
    webhooks,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, log_structured

settings = get_settings()
if settings.APP_ENV in {"local", "test"}:
    email_validator.TEST_ENVIRONMENT = True
configure_logging(settings.LOG_LEVEL)

_production = settings.APP_ENV == "production"
app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
    openapi_url=None if _production else "/openapi.json",
)

# CORS explícito para el origen web; sin "*" porque la sesión usa cookies.
_local_origin_regex = (
    r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
    if settings.APP_ENV in {"local", "test"}
    else None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.WEB_BASE_URL).rstrip("/")],
    allow_origin_regex=_local_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-Organization-ID", "X-Request-ID", "Content-Type"],
)

_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "too_many_requests",
    503: "service_unavailable",
}

_MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_AUTH_LIMIT_WINDOW_SECONDS = 60.0
_AUTH_LIMIT_MAX_ATTEMPTS = 60
_AUTH_LIMIT_ENVS = frozenset({"staging", "production"})
_AUTH_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
    }
)
_auth_attempts: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _request_id(request: Request) -> str:
    value: object = getattr(request.state, "request_id", None)
    return str(value) if value else "unknown"


@app.middleware("http")
async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    correlation_id = request.headers.get("X-Correlation-ID")
    # organization_id se poblará desde la sesión autorizada en Fase 2; nunca desde headers.
    organization_id: str | None = None

    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    request.state.organization_id = organization_id

    response_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    redirect: Response | None = None
    if settings.APP_ENV == "production":
        response_headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0]
        scheme = forwarded.strip().lower() or request.url.scheme.lower()
        if scheme != "https":
            location = f"https://{request.url.netloc}{request.url.path}"
            if request.url.query:
                location = f"{location}?{request.url.query}"
            redirect = RedirectResponse(
                url=location, status_code=status.HTTP_307_TEMPORARY_REDIRECT
            )
        else:
            response_headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

    too_large = False
    if (
        redirect is None
        and request.method in _BODY_METHODS
        and not request.headers.get("content-type", "")
        .lower()
        .startswith("multipart/form-data")
    ):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > _MAX_REQUEST_BODY_BYTES:
            too_large = True
        else:
            body = await request.body()
            if len(body) > _MAX_REQUEST_BODY_BYTES:
                too_large = True

    if redirect is not None:
        response = redirect
    elif too_large:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={
                "error": {
                    "code": _ERROR_CODES[status.HTTP_413_CONTENT_TOO_LARGE],
                    "message": "Solicitud demasiado grande.",
                    "request_id": request_id,
                }
            },
        )
    elif (
        settings.APP_ENV in _AUTH_LIMIT_ENVS
        and request.method == "POST"
        and request.url.path in _AUTH_PATHS
    ):
        now = monotonic()
        attempts = _auth_attempts[_client_ip(request)]
        while attempts and now - attempts[0] >= _AUTH_LIMIT_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _AUTH_LIMIT_MAX_ATTEMPTS:
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": _ERROR_CODES[status.HTTP_429_TOO_MANY_REQUESTS],
                        "message": "Demasiadas solicitudes; intente nuevamente más tarde.",
                        "request_id": request_id,
                    }
                },
                headers={"Retry-After": str(int(_AUTH_LIMIT_WINDOW_SECONDS))},
            )
        else:
            attempts.append(now)
            response = await call_next(request)
    else:
        response = await call_next(request)

    response.headers.update(response_headers)
    response.headers["X-Request-ID"] = request_id
    if correlation_id:
        response.headers["X-Correlation-ID"] = correlation_id

    log_structured(
        logging.INFO,
        "http_request_completed",
        request_id=request_id,
        correlation_id=correlation_id,
        organization_id=organization_id,
    )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "No se pudo completar la solicitud."
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": _ERROR_CODES.get(exc.status_code, "http_error"),
                "message": message,
                "request_id": _request_id(request),
            }
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    # exc.errors() puede incluir valores personales: no se registran ni se devuelven.
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Solicitud inválida; revise los campos enviados.",
                "request_id": _request_id(request),
            }
        },
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(applications.router)
app.include_router(documents.router)
app.include_router(assessment.router)
app.include_router(agents.router)
app.include_router(analytics.router)
app.include_router(interviews.router)
app.include_router(automation.router)
app.include_router(integrations.router)
app.include_router(webhooks.router)
