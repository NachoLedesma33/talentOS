from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.applications.models import Application, ApplicationSource, ApplicationStage, StageChange
from app.applications.repositories import (
    count_applications as count_application_rows,
)
from app.applications.repositories import (
    get_application as get_application_row,
)
from app.applications.repositories import (
    list_applications as list_application_rows,
)
from app.applications.repositories import (
    list_stage_changes as list_stage_change_rows,
)
from app.audit.service import record_audit
from app.candidates.repositories import get_candidate as get_candidate_row
from app.core.logging import log_structured
from app.identity.repositories import get_membership
from app.jobs.repositories import get_job as get_job_row


class ApplicationsDomainError(Exception):
    """Error determinista del dominio de postulaciones."""


class ApplicationValidationError(ApplicationsDomainError):
    """Dato de entrada inválido según las reglas del dominio."""


class ApplicationNotFoundError(ApplicationsDomainError):
    """La postulación no existe en la organización autenticada."""


class RelatedResourceNotFoundError(ApplicationsDomainError):
    """La vacante o el candidato no existen en la organización autenticada."""


class DuplicateApplicationError(ApplicationsDomainError):
    """El candidato ya está postulado a esa vacante en la organización."""


class InvalidStageTransitionError(ApplicationsDomainError):
    """La transición de etapa solicitada no está permitida."""


_ALLOWED_TRANSITIONS: dict[ApplicationStage, frozenset[ApplicationStage]] = {
    ApplicationStage.APPLIED: frozenset(
        {ApplicationStage.SCREENING, ApplicationStage.REJECTED}
    ),
    ApplicationStage.SCREENING: frozenset(
        {ApplicationStage.INTERVIEW, ApplicationStage.REJECTED}
    ),
    ApplicationStage.INTERVIEW: frozenset({ApplicationStage.OFFER, ApplicationStage.REJECTED}),
    ApplicationStage.OFFER: frozenset({ApplicationStage.HIRED, ApplicationStage.REJECTED}),
    ApplicationStage.HIRED: frozenset(),
    ApplicationStage.REJECTED: frozenset(),
}


def _require_application(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> Application:
    application = get_application_row(db, organization_id, application_id)
    if application is None:
        raise ApplicationNotFoundError
    return application


def get_application(
    db: DBSession, *, organization_id: uuid.UUID, application_id: uuid.UUID
) -> Application:
    """Expone la postulación propia al router; el repositorio filtra por tenant."""
    return _require_application(db, organization_id, application_id)


def list_applications(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    stage: ApplicationStage | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Application], int]:
    """Devuelve la página de postulaciones del tenant y el total sin paginar."""
    applications = list_application_rows(
        db,
        organization_id,
        job_id=job_id,
        candidate_id=candidate_id,
        stage=stage,
        limit=limit,
        offset=offset,
    )
    total = count_application_rows(
        db, organization_id, job_id=job_id, candidate_id=candidate_id, stage=stage
    )
    return applications, total


def create_application(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    source: ApplicationSource | None = None,
    actor_id: uuid.UUID | None = None,
) -> Application:
    """Asocia un candidato y una vacante propios; etapa inicial `applied`."""
    if get_job_row(db, organization_id, job_id) is None:
        raise RelatedResourceNotFoundError("job")
    if get_candidate_row(db, organization_id, candidate_id) is None:
        raise RelatedResourceNotFoundError("candidate")
    if count_application_rows(db, organization_id, job_id=job_id, candidate_id=candidate_id):
        raise DuplicateApplicationError

    application = Application(
        organization_id=organization_id,
        job_id=job_id,
        candidate_id=candidate_id,
        source=source,
        stage=ApplicationStage.APPLIED,
    )
    db.add(application)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicateApplicationError from None

    initial_change = StageChange(
        application_id=application.id,
        from_stage=None,
        to_stage=ApplicationStage.APPLIED,
        actor_id=actor_id,
    )
    db.add(initial_change)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="application.created",
        resource_type="application",
        resource_id=application.id,
    )
    db.commit()
    return application


def change_stage(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    to_stage: ApplicationStage,
    actor_id: uuid.UUID | None = None,
    note: str | None = None,
    automation_run_id: uuid.UUID | None = None,
    dispatch_event: bool = True,
) -> StageChange:
    """Aplica solo transiciones permitidas; `hired` y `rejected` son terminales.

    `automation_run_id` solo etiqueta la traza; no altera la transición ni la
    auditoría. El dispatch es local, posterior al commit y lazy para evitar el
    ciclo de imports con `app.automation.service`.
    """
    application = _require_application(db, organization_id, application_id)
    if to_stage not in _ALLOWED_TRANSITIONS.get(application.stage, frozenset()):
        raise InvalidStageTransitionError

    clean_note = note.strip() if note is not None else None
    if note is not None and not clean_note:
        raise ApplicationValidationError("note must not be blank")

    change = StageChange(
        application_id=application.id,
        from_stage=application.stage,
        to_stage=to_stage,
        actor_id=actor_id,
        note=clean_note,
    )
    application.stage = to_stage
    db.add(change)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="application.stage_changed",
        resource_type="application",
        resource_id=application.id,
    )
    db.commit()
    if dispatch_event:
        _dispatch_stage_changed(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            change_id=change.id,
            automation_run_id=automation_run_id,
        )
    return change


def _dispatch_stage_changed(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    change_id: uuid.UUID,
    automation_run_id: uuid.UUID | None,
) -> None:
    """Dispara reglas activas sin revertir el cambio si el motor falla."""
    try:
        if actor_id is None:
            return
        membership = get_membership(db, actor_id, organization_id)
        if membership is None:
            return
        from app.automation.service import dispatch_domain_event

        dispatch_domain_event(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            actor_role=membership.role,
            trigger_event_id=change_id,
            correlation_id=automation_run_id or change_id,
        )
    except Exception:
        log_structured(
            logging.WARNING,
            "automation.dispatch_failed",
            correlation_id=str(automation_run_id or change_id),
            organization_id=str(organization_id),
        )


def list_stage_changes(
    db: DBSession, *, organization_id: uuid.UUID, application_id: uuid.UUID
) -> list[StageChange]:
    """Lista el historial de una postulación verificada en la organización activa."""
    _require_application(db, organization_id, application_id)
    return list_stage_change_rows(db, organization_id, application_id)
