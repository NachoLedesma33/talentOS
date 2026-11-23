from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

_LOGGER = logging.getLogger("talentos")
_HANDLER_FLAG = "_talentos_json_handler"


class JsonFormatter(logging.Formatter):
    """JSON con metadatos de correlación; nunca payloads, CVs ni secretos."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "organization_id": getattr(record, "organization_id", None),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Instala el formateador JSON una sola vez y fija el nivel del root logger."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    if any(getattr(handler, _HANDLER_FLAG, False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    setattr(handler, _HANDLER_FLAG, True)
    root.addHandler(handler)


def log_structured(
    level: int,
    message: str,
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Registra solo identificadores y un mensaje controlado, sin datos de candidato."""
    _LOGGER.log(
        level,
        message,
        extra={
            "request_id": request_id,
            "correlation_id": correlation_id,
            "organization_id": organization_id,
        },
    )
