from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]  # Celery 5.4 no publica stubs PEP 561.
from celery.schedules import crontab  # type: ignore[import-untyped]

from app.core.config import get_settings

settings = get_settings()

# Sin importar app.main: el worker solo necesita configuración tipada y sus tareas.
celery_app = Celery(
    "talentos",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=60,
    task_time_limit=90,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "purge-old-agent-events": {
            "task": "agents.purge_old_events",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
