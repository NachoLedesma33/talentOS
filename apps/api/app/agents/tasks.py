from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.agents import service as agents_service
from app.agents.repositories import get_agent_run
from app.core.logging import log_structured
from app.db.session import SessionLocal
from app.identity.models import MembershipRole
from app.workers.celery_app import celery_app


def _log_event(
    level: int,
    event: str,
    *,
    agent_run_id: uuid.UUID | str,
    organization_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str,
    result: str,
    error_code: str | None = None,
) -> None:
    """Log de una línea: solo IDs, código estable y resultado; nunca CV ni secretos."""
    message = f"{event} agent_run_id={agent_run_id} result={result}"
    if error_code:
        message += f" error_code={error_code}"
    log_structured(
        level,
        message,
        correlation_id=str(correlation_id),
        organization_id=str(organization_id),
    )


@celery_app.task(name="agents.resume_workflow")  # type: ignore[untyped-decorator]
def resume_agent_workflow(
    organization_id: str,
    actor_id: str,
    actor_role: str,
    agent_run_id: str,
    correlation_id: str,
) -> None:
    """Reanuda un run ya aprobado, con sesión propia y tenant verificado antes del grafo."""
    try:
        org_id = uuid.UUID(organization_id)
        run_id = uuid.UUID(agent_run_id)
        actor = uuid.UUID(actor_id)
        correlation = uuid.UUID(correlation_id)
        role = MembershipRole(str(actor_role))
    except (TypeError, ValueError):
        _log_event(
            logging.WARNING,
            "agent.resume_rejected",
            agent_run_id=agent_run_id,
            organization_id=organization_id,
            correlation_id=correlation_id,
            result="aborted",
            error_code="invalid_context",
        )
        return

    db: DBSession = SessionLocal()
    try:
        run = get_agent_run(db, org_id, run_id)
        if run is None:
            _log_event(
                logging.WARNING,
                "agent.resume_rejected",
                agent_run_id=run_id,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="not_found",
            )
            return
        # El tenant viaja explícitamente y se comprueba antes de tocar el grafo.
        if run.organization_id != org_id:
            _log_event(
                logging.WARNING,
                "agent.resume_rejected",
                agent_run_id=run_id,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="organization_mismatch",
            )
            return
        if run.correlation_id != correlation:
            _log_event(
                logging.WARNING,
                "agent.resume_rejected",
                agent_run_id=run_id,
                organization_id=org_id,
                correlation_id=correlation,
                result="aborted",
                error_code="correlation_mismatch",
            )
            return

        result = agents_service.resume_workflow(
            db,
            organization_id=org_id,
            actor_id=actor,
            actor_role=role,
            agent_run_id=run_id,
        )
        db.commit()
        _log_event(
            logging.INFO,
            "agent.resume_completed",
            agent_run_id=run_id,
            organization_id=org_id,
            correlation_id=correlation,
            result=str(result.get("status", "unknown")),
        )
    except SQLAlchemyError:
        db.rollback()
        _log_event(
            logging.ERROR,
            "agent.resume_failed",
            agent_run_id=run_id,
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
            "agent.resume_failed",
            agent_run_id=run_id,
            organization_id=org_id,
            correlation_id=correlation,
            result="failed",
            error_code="internal_error",
        )
    finally:
        db.close()
