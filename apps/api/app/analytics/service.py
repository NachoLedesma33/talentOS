from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.agents.models import AgentRun, AgentRunStatus
from app.applications.models import Application, ApplicationStage, StageChange
from app.assessment.models import Assessment, AssessmentStatus, RequirementEvaluation
from app.automation.models import AutomationRun, AutomationRunMode, AutomationRunStatus
from app.jobs.models import Job, JobStatus

_PIPELINE_ORDER: tuple[ApplicationStage, ...] = (
    ApplicationStage.APPLIED,
    ApplicationStage.SCREENING,
    ApplicationStage.INTERVIEW,
    ApplicationStage.OFFER,
    ApplicationStage.HIRED,
)


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    name: str
    description: str
    unit: str
    is_estimate: bool


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    value: float
    unit: str
    is_estimate: bool


class StageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: ApplicationStage
    applications: int
    arrivals: int
    exits: int
    avg_days_in_stage: float | None
    total_days_in_stage: float


class PipelineReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    jobs_open: int
    jobs_closed: int
    stages: tuple[StageMetric, ...]
    conversions: tuple[Metric, ...]
    avg_process_days: float | None
    definitions: tuple[MetricDefinition, ...]


PIPELINE_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="jobs_open",
        name="Vacantes abiertas",
        description="Vacantes con status 'open' pertenecientes al tenant; dato real.",
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="jobs_closed",
        name="Vacantes cerradas",
        description="Vacantes con status 'closed' pertenecientes al tenant; dato real.",
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="candidates_by_stage",
        name="Candidatos por etapa",
        description="Postulaciones agrupadas por etapa actual; dato real.",
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="time_in_stage",
        name="Tiempo por etapa",
        description=(
            "Días entre el evento de entrada a una etapa y el siguiente evento. "
            "Para la primera etapa se usa created_at de la postulación. "
            "Estimación derivada de marcas de tiempo, no duración contractual."
        ),
        unit="days",
        is_estimate=True,
    ),
    MetricDefinition(
        key="conversion",
        name="Conversión entre etapas",
        description=(
            "Postulaciones que alcanzaron la etapa siguiente divididas por las que "
            "alcanzaron la etapa actual; 0 cuando no hay denominador. Dato real."
        ),
        unit="ratio",
        is_estimate=False,
    ),
    MetricDefinition(
        key="total_process_days",
        name="Tiempo total de proceso",
        description=(
            "Media de días entre created_at y el último cambio de etapa por postulación; "
            "estimación derivada de marcas de tiempo."
        ),
        unit="days",
        is_estimate=True,
    ),
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _days_between(start: datetime, end: datetime) -> float:
    return max(0.0, (_as_utc(end) - _as_utc(start)).total_seconds() / 86400)


def _round(value: float) -> float:
    return round(value, 3)


def _count_jobs(db: DBSession, organization_id: uuid.UUID) -> tuple[int, int]:
    opened = 0
    closed = 0
    stmt = (
        select(Job.status, func.count())
        .where(Job.organization_id == organization_id)
        .group_by(Job.status)
    )
    for status, total in db.execute(stmt):
        if status is JobStatus.OPEN:
            opened = int(total)
        elif status is JobStatus.CLOSED:
            closed = int(total)
    return opened, closed


def _count_applications_by_stage(
    db: DBSession, organization_id: uuid.UUID
) -> dict[ApplicationStage, int]:
    counts = {stage: 0 for stage in ApplicationStage}
    stmt = (
        select(Application.stage, func.count())
        .where(Application.organization_id == organization_id)
        .group_by(Application.stage)
    )
    for stage, total in db.execute(stmt):
        counts[stage] = int(total)
    return counts


def _application_timestamps(
    db: DBSession, organization_id: uuid.UUID
) -> dict[uuid.UUID, datetime]:
    result: dict[uuid.UUID, datetime] = {}
    stmt = select(Application.id, Application.created_at).where(
        Application.organization_id == organization_id
    )
    for application_id, created_at in db.execute(stmt):
        result[application_id] = created_at
    return result


def _stage_changes(
    db: DBSession, organization_id: uuid.UUID
) -> list[tuple[uuid.UUID, ApplicationStage | None, ApplicationStage, datetime]]:
    stmt = (
        select(
            StageChange.application_id,
            StageChange.from_stage,
            StageChange.to_stage,
            StageChange.created_at,
        )
        .join(Application, Application.id == StageChange.application_id)
        .where(Application.organization_id == organization_id)
        .order_by(StageChange.application_id, StageChange.created_at, StageChange.id)
    )
    return [
        (row[0], row[1], row[2], row[3]) for row in db.execute(stmt).all()
    ]


def compute_pipeline_report(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> PipelineReport:
    """Métricas del pipeline del tenant; sin datos personales ni inferencias."""
    generated_at = _as_utc(now) if now is not None else datetime.now(UTC)
    jobs_open, jobs_closed = _count_jobs(db, organization_id)
    applications_by_stage = _count_applications_by_stage(db, organization_id)
    created_at_by_application = _application_timestamps(db, organization_id)

    arrivals: dict[ApplicationStage, int] = defaultdict(int)
    exits: dict[ApplicationStage, int] = defaultdict(int)
    reached: dict[ApplicationStage, set[uuid.UUID]] = defaultdict(set)
    durations: dict[ApplicationStage, list[float]] = defaultdict(list)
    total_by_application: dict[uuid.UUID, float] = defaultdict(float)
    last_at_by_application: dict[uuid.UUID, datetime] = {}
    last_stage_by_application: dict[uuid.UUID, ApplicationStage] = {}

    for application_id, from_stage, to_stage, changed_at in _stage_changes(
        db, organization_id
    ):
        arrivals[to_stage] += 1
        reached[to_stage].add(application_id)
        if from_stage is None:
            if to_stage is not ApplicationStage.APPLIED:
                arrivals[ApplicationStage.APPLIED] += 1
                reached[ApplicationStage.APPLIED].add(application_id)
                exits[ApplicationStage.APPLIED] += 1
        else:
            exits[from_stage] += 1

        start: datetime
        effective_from: ApplicationStage
        if application_id in last_stage_by_application:
            start = last_at_by_application[application_id]
            effective_from = last_stage_by_application[application_id]
        else:
            created = created_at_by_application.get(application_id)
            if created is None:
                continue
            start = created
            effective_from = ApplicationStage.APPLIED

        elapsed = _days_between(start, changed_at)
        durations[effective_from].append(elapsed)
        total_by_application[application_id] += elapsed
        last_at_by_application[application_id] = changed_at
        last_stage_by_application[application_id] = to_stage

    stages = tuple(
        StageMetric(
            stage=stage,
            applications=applications_by_stage[stage],
            arrivals=arrivals[stage],
            exits=exits[stage],
            avg_days_in_stage=(
                _round(sum(durations[stage]) / len(durations[stage]))
                if durations[stage]
                else None
            ),
            total_days_in_stage=_round(sum(durations[stage])),
        )
        for stage in ApplicationStage
    )

    conversions: list[Metric] = []
    for current, following in zip(_PIPELINE_ORDER, _PIPELINE_ORDER[1:], strict=False):
        denominator = len(reached[current])
        value = len(reached[following]) / denominator if denominator else 0.0
        conversions.append(
            Metric(
                key=f"conversion.{current.value}.{following.value}",
                value=_round(value),
                unit="ratio",
                is_estimate=False,
            )
        )

    avg_process_days = (
        _round(sum(total_by_application.values()) / len(total_by_application))
        if total_by_application
        else None
    )
    return PipelineReport(
        generated_at=generated_at,
        jobs_open=jobs_open,
        jobs_closed=jobs_closed,
        stages=stages,
        conversions=tuple(conversions),
        avg_process_days=avg_process_days,
        definitions=PIPELINE_DEFINITIONS,
    )


ESTIMATED_MINUTES_PER_AUTOMATION_RUN = 5


class OperationalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    assessments_pending_review: int
    agent_runs_completed: int
    agent_runs_failed: int
    automation_runs_executed: int
    estimated_minutes_saved: float
    estimates_basis: str
    definitions: tuple[MetricDefinition, ...]


class AnalyticsOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    pipeline: PipelineReport
    operational: OperationalReport


OPERATIONAL_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="assessments_pending_review",
        name="Evaluaciones pendientes de revisión",
        description=(
            "Evaluaciones con status 'pending' o 'needs_review', o con algún "
            "requisito en revisión; dato real del tenant."
        ),
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="agent_runs_completed",
        name="Ejecuciones de agentes exitosas",
        description="AgentRuns con status 'completed' del tenant; dato real.",
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="agent_runs_failed",
        name="Ejecuciones de agentes fallidas",
        description="AgentRuns con status 'failed' del tenant; dato real.",
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="automation_runs_executed",
        name="Automatizaciones ejecutadas",
        description=(
            "AutomationRuns en modo 'live' con status 'completed' del tenant; dato real."
        ),
        unit="count",
        is_estimate=False,
    ),
    MetricDefinition(
        key="estimated_minutes_saved",
        name="Tiempo estimado ahorrado",
        description=(
            f"{ESTIMATED_MINUTES_PER_AUTOMATION_RUN} minutos por automatización live completada; "
            "supuesto declarado, no medición ni coste monetario."
        ),
        unit="minutes",
        is_estimate=True,
    ),
)


def _count_assessments_pending_review(
    db: DBSession, organization_id: uuid.UUID
) -> int:
    ids: set[uuid.UUID] = set()
    status_stmt = select(Assessment.id).where(
        Assessment.organization_id == organization_id,
        or_(
            Assessment.status == AssessmentStatus.PENDING,
            Assessment.status == AssessmentStatus.NEEDS_REVIEW,
        ),
    )
    ids.update(row[0] for row in db.execute(status_stmt))
    review_stmt = (
        select(Assessment.id)
        .join(
            RequirementEvaluation,
            RequirementEvaluation.assessment_id == Assessment.id,
        )
        .where(
            Assessment.organization_id == organization_id,
            RequirementEvaluation.review_required.is_(True),
        )
    )
    ids.update(row[0] for row in db.execute(review_stmt))
    return len(ids)


def _count_agent_runs(
    db: DBSession, organization_id: uuid.UUID
) -> tuple[int, int]:
    completed = 0
    failed = 0
    stmt = (
        select(AgentRun.status, func.count())
        .where(AgentRun.organization_id == organization_id)
        .group_by(AgentRun.status)
    )
    for status, total in db.execute(stmt):
        if status == AgentRunStatus.COMPLETED:
            completed = int(total)
        elif status == AgentRunStatus.FAILED:
            failed = int(total)
    return completed, failed


def _count_automation_runs_executed(
    db: DBSession, organization_id: uuid.UUID
) -> int:
    stmt = select(func.count()).select_from(AutomationRun).where(
        AutomationRun.organization_id == organization_id,
        AutomationRun.status == AutomationRunStatus.COMPLETED,
        AutomationRun.mode == AutomationRunMode.LIVE,
    )
    return int(db.scalar(stmt) or 0)


def compute_operational_report(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> OperationalReport:
    """Métricas operativas del tenant; separa dato real de supuesto declarado."""
    generated_at = _as_utc(now) if now is not None else datetime.now(UTC)
    pending = _count_assessments_pending_review(db, organization_id)
    completed_runs, failed_runs = _count_agent_runs(db, organization_id)
    executed = _count_automation_runs_executed(db, organization_id)
    return OperationalReport(
        generated_at=generated_at,
        assessments_pending_review=pending,
        agent_runs_completed=completed_runs,
        agent_runs_failed=failed_runs,
        automation_runs_executed=executed,
        estimated_minutes_saved=_round(
            executed * ESTIMATED_MINUTES_PER_AUTOMATION_RUN
        ),
        estimates_basis=(
            f"{ESTIMATED_MINUTES_PER_AUTOMATION_RUN} min por ejecución live completada; "
            "supuesto no medido, sin coste monetario"
        ),
        definitions=OPERATIONAL_DEFINITIONS,
    )


def build_analytics_overview(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> AnalyticsOverview:
    """Vista combinada; ambas secciones comparten instante y filtro de tenant."""
    generated_at = _as_utc(now) if now is not None else datetime.now(UTC)
    return AnalyticsOverview(
        generated_at=generated_at,
        pipeline=compute_pipeline_report(db, organization_id, now=generated_at),
        operational=compute_operational_report(db, organization_id, now=generated_at),
    )
