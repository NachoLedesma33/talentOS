from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
configure_logging(settings.LOG_LEVEL)

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

# CORS explícito para el origen web; sin "*" porque la sesión usa cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.WEB_BASE_URL).rstrip("/")],
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
    422: "validation_error",
    429: "too_many_requests",
    503: "service_unavailable",
}


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

    response = await call_next(request)
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
