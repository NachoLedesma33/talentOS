"""Tarea de ejecución diferida de automatizaciones.

El contexto mínimo viaja desde la API; la tarea abre su propia sesión y
verifica tenant, ejecución y correlación antes de delegar en el dominio.
Solo registra IDs, códigos de error y resultado: nunca CV, secretos ni notas.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.automation import service as automation_service
from app.automation.models import AutomationRun
from app.core.logging import log_structured
from app.db.session import SessionLocal
from app.identity.models import MembershipRole
from app.workers.celery_app import celery_app


def _log_event(
    level: int,
    event: str,
    *,
    run_id: uuid.UUID | str,
    organization_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log estructurado de una línea: solo identificadores y código estable."""
    message = f"{event} run_id={run_id} result={result}"
    if error_code:
        message += f" error_code={error_code}"
    log_structured(
        level,
        message,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name="automation.execute_run", acks_late=True, reject_on_worker_lost=True
)
def execute_run(
    organization_id: str,
    actor_id: str,
    actor_role: str,
    run_id: str,
    correlation_id: str,
) -> None:
    """Ejecuta una corrida pendiente con sesión propia y contexto verificado."""
    try:
        org_id = uuid.UUID(organization_id)
        actor = uuid.UUID(actor_id)
        target_run = uuid.UUID(run_id)
        correlation = uuid.UUID(correlation_id)
        role = MembershipRole(str(actor_role))
    except (TypeError, ValueError):
        _log_event(
            logging.WARNING,
            "automation.run_rejected",
            run_id=run_id,
            organization_id=organization_id,
            correlation_id=correlation_id,
            result="aborted",
            error_code="invalid_context",
        )
        return

    db: DBSession = SessionLocal()
    try:
        # Se localiza por ID y luego se comprueba el tenant explícitamente: así
        # un run ajeno se distingue de uno inexistente sin exponer su contenido.
        run = db.get(AutomationRun, target_run)
        if run is None:
            _log_event(
                logging.WARNING,
                "automation.run_rejected",
                run_id=target_run,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="not_found",
            )
            return
        if run.organization_id != org_id:
            _log_event(
                logging.WARNING,
                "automation.run_rejected",
                run_id=target_run,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="organization_mismatch",
            )
            return
        if run.correlation_id != correlation:
            _log_event(
                logging.WARNING,
                "automation.run_rejected",
                run_id=target_run,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="correlation_mismatch",
            )
            return

        result = automation_service.execute_pending_run(
            db,
            organization_id=org_id,
            actor_id=actor,
            actor_role=role,
            run_id=target_run,
            correlation_id=correlation,
        )
        db.commit()
        _log_event(
            logging.INFO,
            "automation.run_executed",
            run_id=target_run,
            organization_id=org_id,
            correlation_id=correlation,
            result=result.status.value,
        )
    except automation_service.AutomationServiceError as exc:
        db.rollback()
        _log_event(
            logging.WARNING,
            "automation.run_rejected",
            run_id=target_run,
            organization_id=org_id,
            correlation_id=correlation,
            result="aborted",
            error_code=exc.code,
        )
    except SQLAlchemyError:
        db.rollback()
        _log_event(
            logging.ERROR,
            "automation.run_failed",
            run_id=target_run,
            organization_id=org_id,
            correlation_id=correlation,
            result="failed",
            error_code="database_unavailable",
        )
    except Exception:
        # Ninguna excepción de librería sube al worker: evitar trazas con datos del candidato.
        db.rollback()
        _log_event(
            logging.ERROR,
            "automation.run_failed",
            run_id=target_run,
            organization_id=org_id,
            correlation_id=correlation,
            result="failed",
            error_code="internal_error",
        )
    finally:
        db.close()
