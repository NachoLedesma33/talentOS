from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

from app.agents.models import AgentRun, AgentRunStatus
from app.analytics.service import (
    ESTIMATED_MINUTES_PER_AUTOMATION_RUN,
    build_analytics_overview,
    compute_operational_report,
    compute_pipeline_report,
)
from app.applications.models import Application, ApplicationStage, StageChange
from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)
from app.automation.models import (
    Automation,
    AutomationRun,
    AutomationRunMode,
    AutomationRunStatus,
    AutomationStatus,
)
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Organization, User
from app.jobs.models import Job, JobStatus, JobVersion

_TENANT_A = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-tenant-a")
_TENANT_B = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-tenant-b")
_OWNER = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-owner")
_NOW = datetime(2026, 1, 10, tzinfo=UTC)
_START = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine, expire_on_commit=False) as session:
        yield session


def _seed(db: DBSession) -> None:
    db.add_all(
        [
            Organization(id=_TENANT_A, name="Synthetic Org A", slug="analytics-a"),
            Organization(id=_TENANT_B, name="Synthetic Org B", slug="analytics-b"),
            User(
                id=_OWNER,
                email="owner@example.test",
                password_hash="synthetic",
                name="Synthetic Owner",
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            Job(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-job-open"),
                organization_id=_TENANT_A,
                owner_id=_OWNER,
                title="Synthetic open role",
                status=JobStatus.OPEN,
            ),
            Job(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-job-closed"),
                organization_id=_TENANT_A,
                owner_id=_OWNER,
                title="Synthetic closed role",
                status=JobStatus.CLOSED,
            ),
            Job(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-job-tenant-b"),
                organization_id=_TENANT_B,
                owner_id=_OWNER,
                title="Foreign role",
                status=JobStatus.OPEN,
            ),
        ]
    )
    db.flush()

    job_id = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-job-open")
    foreign_job_id = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-job-tenant-b")
    candidate_a = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-candidate-a")
    candidate_b = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-candidate-b")
    candidate_foreign = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-candidate-foreign")
    db.add_all(
        [
            Candidate(
                id=candidate_a,
                organization_id=_TENANT_A,
                name="Synthetic Candidate A",
                email="candidate-a@example.test",
            ),
            Candidate(
                id=candidate_b,
                organization_id=_TENANT_A,
                name="Synthetic Candidate B",
                email="candidate-b@example.test",
            ),
            Candidate(
                id=candidate_foreign,
                organization_id=_TENANT_B,
                name="Foreign Candidate",
                email="foreign@example.test",
            ),
        ]
    )
    db.flush()

    application_a = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-application-a")
    application_b = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-application-b")
    application_foreign = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-application-foreign")
    db.add_all(
        [
            Application(
                id=application_a,
                organization_id=_TENANT_A,
                job_id=job_id,
                candidate_id=candidate_a,
                stage=ApplicationStage.INTERVIEW,
                created_at=_START,
            ),
            Application(
                id=application_b,
                organization_id=_TENANT_A,
                job_id=job_id,
                candidate_id=candidate_b,
                stage=ApplicationStage.SCREENING,
                created_at=_START,
            ),
            Application(
                id=application_foreign,
                organization_id=_TENANT_B,
                job_id=foreign_job_id,
                candidate_id=candidate_foreign,
                stage=ApplicationStage.HIRED,
                created_at=_START,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            StageChange(
                application_id=application_a,
                from_stage=None,
                to_stage=ApplicationStage.SCREENING,
                created_at=_START + timedelta(days=1),
            ),
            StageChange(
                application_id=application_a,
                from_stage=ApplicationStage.SCREENING,
                to_stage=ApplicationStage.INTERVIEW,
                created_at=_START + timedelta(days=4),
            ),
            StageChange(
                application_id=application_b,
                from_stage=None,
                to_stage=ApplicationStage.SCREENING,
                created_at=_START + timedelta(days=2),
            ),
            StageChange(
                application_id=application_foreign,
                from_stage=None,
                to_stage=ApplicationStage.HIRED,
                created_at=_START + timedelta(days=9),
            ),
        ]
    )

    job_version_id = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-job-version")
    db.add(
        JobVersion(id=job_version_id, job_id=job_id, version=1, snapshot={})
    )
    db.flush()
    assessment_review = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-assessment-review")
    assessment_flagged = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-assessment-flagged")
    assessment_done = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-assessment-done")
    assessment_foreign = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-assessment-foreign")
    db.add_all(
        [
            Assessment(
                id=assessment_review,
                organization_id=_TENANT_A,
                application_id=application_a,
                job_version_id=job_version_id,
                candidate_id=candidate_a,
                status=AssessmentStatus.NEEDS_REVIEW,
                model_version="synthetic-v1",
                prompt_version="evaluation-v1",
                created_by=_OWNER,
            ),
            Assessment(
                id=assessment_flagged,
                organization_id=_TENANT_A,
                application_id=application_b,
                job_version_id=job_version_id,
                candidate_id=candidate_b,
                status=AssessmentStatus.COMPLETED,
                model_version="synthetic-v1",
                prompt_version="evaluation-v1",
                created_by=_OWNER,
            ),
            Assessment(
                id=assessment_done,
                organization_id=_TENANT_A,
                application_id=application_b,
                job_version_id=job_version_id,
                candidate_id=candidate_b,
                status=AssessmentStatus.COMPLETED,
                model_version="synthetic-v1",
                prompt_version="evaluation-v2",
                created_by=_OWNER,
            ),
            Assessment(
                id=assessment_foreign,
                organization_id=_TENANT_B,
                application_id=application_foreign,
                job_version_id=job_version_id,
                candidate_id=candidate_foreign,
                status=AssessmentStatus.NEEDS_REVIEW,
                model_version="synthetic-v1",
                prompt_version="evaluation-v1",
                created_by=_OWNER,
            ),
        ]
    )
    db.flush()
    db.add(
        RequirementEvaluation(
            assessment_id=assessment_flagged,
            requirement_id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-requirement"),
            status=RequirementEvaluationStatus.NEEDS_REVIEW,
            explanation="synthetic review flag",
            review_required=True,
        )
    )

    automation_id = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-automation")
    foreign_automation_id = uuid.uuid5(uuid.NAMESPACE_URL, "analytics-automation-foreign")
    db.add_all(
        [
            Automation(
                id=automation_id,
                organization_id=_TENANT_A,
                name="Synthetic automation",
                status=AutomationStatus.ACTIVE,
                created_by=_OWNER,
            ),
            Automation(
                id=foreign_automation_id,
                organization_id=_TENANT_B,
                name="Foreign automation",
                status=AutomationStatus.ACTIVE,
                created_by=_OWNER,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            AgentRun(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-run-completed"),
                organization_id=_TENANT_A,
                workflow="cv_analysis",
                version="v1",
                status=AgentRunStatus.COMPLETED,
                idempotency_key="analytics-run-completed",
                correlation_id=uuid.uuid4(),
                actor_id=_OWNER,
            ),
            AgentRun(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-run-failed"),
                organization_id=_TENANT_A,
                workflow="cv_analysis",
                version="v1",
                status=AgentRunStatus.FAILED,
                idempotency_key="analytics-run-failed",
                correlation_id=uuid.uuid4(),
                actor_id=_OWNER,
            ),
            AgentRun(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-run-foreign"),
                organization_id=_TENANT_B,
                workflow="cv_analysis",
                version="v1",
                status=AgentRunStatus.COMPLETED,
                idempotency_key="analytics-run-foreign",
                correlation_id=uuid.uuid4(),
                actor_id=_OWNER,
            ),
        ]
    )
    db.add_all(
        [
            AutomationRun(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-automation-run-live"),
                organization_id=_TENANT_A,
                automation_id=automation_id,
                version=1,
                mode=AutomationRunMode.LIVE,
                status=AutomationRunStatus.COMPLETED,
                trigger_event_type="application.stage_changed",
                trigger_event_id=uuid.uuid4(),
                idempotency_key="analytics-automation-run-live",
                correlation_id=uuid.uuid4(),
                actor_id=_OWNER,
            ),
            AutomationRun(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-automation-run-test"),
                organization_id=_TENANT_A,
                automation_id=automation_id,
                version=1,
                mode=AutomationRunMode.TEST,
                status=AutomationRunStatus.COMPLETED,
                trigger_event_type="application.stage_changed",
                trigger_event_id=uuid.uuid4(),
                idempotency_key="analytics-automation-run-test",
                correlation_id=uuid.uuid4(),
                actor_id=_OWNER,
            ),
            AutomationRun(
                id=uuid.uuid5(uuid.NAMESPACE_URL, "analytics-automation-run-foreign"),
                organization_id=_TENANT_B,
                automation_id=foreign_automation_id,
                version=1,
                mode=AutomationRunMode.LIVE,
                status=AutomationRunStatus.COMPLETED,
                trigger_event_type="application.stage_changed",
                trigger_event_id=uuid.uuid4(),
                idempotency_key="analytics-automation-run-foreign",
                correlation_id=uuid.uuid4(),
                actor_id=_OWNER,
            ),
        ]
    )
    db.commit()


def test_pipeline_report_is_tenant_scoped_and_documents_method(db: DBSession) -> None:
    _seed(db)

    report = compute_pipeline_report(db, _TENANT_A, now=_NOW)

    assert report.generated_at == _NOW
    assert report.jobs_open == 1
    assert report.jobs_closed == 1
    assert len(report.stages) == len(ApplicationStage)
    by_stage = {metric.stage: metric for metric in report.stages}
    assert by_stage[ApplicationStage.APPLIED].applications == 0
    assert by_stage[ApplicationStage.APPLIED].arrivals == 2
    assert by_stage[ApplicationStage.APPLIED].exits == 2
    assert by_stage[ApplicationStage.APPLIED].avg_days_in_stage == 1.5
    assert by_stage[ApplicationStage.SCREENING].applications == 1
    assert by_stage[ApplicationStage.SCREENING].avg_days_in_stage == 3.0
    assert by_stage[ApplicationStage.INTERVIEW].applications == 1
    assert by_stage[ApplicationStage.INTERVIEW].arrivals == 1
    assert by_stage[ApplicationStage.HIRED].arrivals == 0
    assert report.avg_process_days == 3.0
    conversions = {metric.key: metric.value for metric in report.conversions}
    assert conversions["conversion.applied.screening"] == 1.0
    assert conversions["conversion.screening.interview"] == 0.5
    assert conversions["conversion.interview.offer"] == 0.0
    assert all(not metric.is_estimate for metric in report.conversions)
    estimates = {
        definition.key: definition.is_estimate for definition in report.definitions
    }
    assert estimates["time_in_stage"] is True
    assert estimates["total_process_days"] is True
    assert estimates["candidates_by_stage"] is False


def test_empty_tenant_has_zero_counts_and_explicit_unknowns(db: DBSession) -> None:
    report = compute_pipeline_report(db, uuid.uuid4(), now=_NOW)

    assert report.jobs_open == 0
    assert report.jobs_closed == 0
    assert all(metric.applications == 0 for metric in report.stages)
    assert all(metric.avg_days_in_stage is None for metric in report.stages)
    assert report.avg_process_days is None
    assert all(metric.value == 0.0 for metric in report.conversions)


def test_report_serialization_has_no_candidate_pii(db: DBSession) -> None:
    _seed(db)

    serialized = json.dumps(
        compute_pipeline_report(db, _TENANT_A, now=_NOW).model_dump(mode="json")
    )

    assert "Synthetic Candidate" not in serialized
    assert "@example.test" not in serialized
    assert "Foreign" not in serialized


def test_operational_report_separates_real_counts_from_estimate(db: DBSession) -> None:
    _seed(db)

    report = compute_operational_report(db, _TENANT_A, now=_NOW)

    assert report.generated_at == _NOW
    assert report.assessments_pending_review == 2
    assert report.agent_runs_completed == 1
    assert report.agent_runs_failed == 1
    assert report.automation_runs_executed == 1
    assert report.estimated_minutes_saved == float(ESTIMATED_MINUTES_PER_AUTOMATION_RUN)
    estimates = {
        definition.key: definition.is_estimate for definition in report.definitions
    }
    assert estimates["estimated_minutes_saved"] is True
    assert estimates["agent_runs_completed"] is False
    assert "no medido" in report.estimates_basis
    assert "coste monetario" in report.estimates_basis


def test_overview_shares_instant_and_tenant(db: DBSession) -> None:
    _seed(db)

    overview = build_analytics_overview(db, _TENANT_A, now=_NOW)

    assert overview.generated_at == _NOW
    assert overview.pipeline.generated_at == _NOW
    assert overview.operational.generated_at == _NOW
    assert overview.pipeline.jobs_open == 1
    assert overview.operational.automation_runs_executed == 1
    serialized = json.dumps(overview.model_dump(mode="json"))
    assert "@example.test" not in serialized


def test_operational_report_of_empty_tenant_is_zero(db: DBSession) -> None:
    report = compute_operational_report(db, uuid.uuid4(), now=_NOW)

    assert report.assessments_pending_review == 0
    assert report.agent_runs_completed == 0
    assert report.agent_runs_failed == 0
    assert report.automation_runs_executed == 0
    assert report.estimated_minutes_saved == 0.0
