from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

from app.analytics.service import compute_pipeline_report
from app.applications.models import Application, ApplicationStage, StageChange
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Organization, User
from app.jobs.models import Job, JobStatus

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
