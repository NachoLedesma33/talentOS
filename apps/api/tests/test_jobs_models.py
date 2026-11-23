from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

# Registrar tablas al importar: `test_auth` recarga `app.db.base` al terminar y
# los modelos importados después quedarían en una metadata distinta de `Base`.
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.db.base import Base


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine, expire_on_commit=False) as session:
        yield session


def _reject_flush(db: DBSession, entity: object) -> None:
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(entity)
            db.flush()


def test_job_and_requirement_enums_use_declared_values(db: DBSession) -> None:
    from app.jobs.models import JobStatus, RequirementCategory, RequirementImportance

    assert [status.value for status in JobStatus] == [
        "draft",
        "open",
        "paused",
        "closed",
        "archived",
    ]
    assert [category.value for category in RequirementCategory] == [
        "skill",
        "experience",
        "education",
        "language",
        "certification",
        "other",
    ]
    assert [importance.value for importance in RequirementImportance] == [
        "required",
        "desirable",
    ]


def test_weight_constraint_rejects_out_of_range_and_unjustified(db: DBSession) -> None:
    from app.identity.models import Organization, User
    from app.jobs.models import (
        Job,
        JobRequirement,
        RequirementCategory,
        RequirementImportance,
    )

    org = Organization(name="Org A", slug="org-a")
    user = User(email="owner-a@example.test", password_hash="synthetic-hash", name="Owner A")
    db.add_all([org, user])
    db.flush()
    job = Job(organization_id=org.id, title="Synthetic role", owner_id=user.id)
    db.add(job)
    db.flush()

    def requirement(weight: float, justification: str) -> JobRequirement:
        return JobRequirement(
            job_id=job.id,
            category=RequirementCategory.SKILL,
            description="Synthetic skill",
            importance=RequirementImportance.REQUIRED,
            weight=weight,
            weight_justification=justification,
        )

    _reject_flush(db, requirement(-0.01, "Negative weight"))
    _reject_flush(db, requirement(1.01, "Weight above one"))
    _reject_flush(db, requirement(0.5, "   "))

    valid = requirement(1.0, "Explicit justification")
    db.add(valid)
    db.flush()
    assert valid.weight == 1.0


def test_job_timestamps_are_utc_and_default_status_is_draft(db: DBSession) -> None:
    from app.identity.models import Organization, User
    from app.jobs.models import Job, JobStatus

    org = Organization(name="Org A", slug="org-a")
    user = User(email="owner-a@example.test", password_hash="synthetic-hash", name="Owner A")
    db.add_all([org, user])
    db.flush()
    job = Job(organization_id=org.id, title="Synthetic role", owner_id=user.id)
    db.add(job)
    db.flush()

    assert job.status is JobStatus.DRAFT
    assert job.created_at.utcoffset() == timedelta(0)
    assert job.updated_at.utcoffset() == timedelta(0)


def test_version_is_unique_per_job(db: DBSession) -> None:
    from app.identity.models import Organization, User
    from app.jobs.models import Job, JobVersion

    org = Organization(name="Org A", slug="org-a")
    user = User(email="owner-a@example.test", password_hash="synthetic-hash", name="Owner A")
    db.add_all([org, user])
    db.flush()
    job = Job(organization_id=org.id, title="Synthetic role", owner_id=user.id)
    other_job = Job(organization_id=org.id, title="Other role", owner_id=user.id)
    db.add_all([job, other_job])
    db.flush()

    first = JobVersion(job_id=job.id, version=1, snapshot={"job": {"title": "A"}})
    db.add(first)
    db.flush()
    _reject_flush(db, JobVersion(job_id=job.id, version=1, snapshot={"job": {"title": "B"}}))

    other = JobVersion(job_id=other_job.id, version=1, snapshot={"job": {"title": "B"}})
    db.add(other)
    db.flush()

    assert len(db.scalars(select(JobVersion)).all()) == 2


def test_deleting_job_cascades_requirements_and_versions(db: DBSession) -> None:
    from app.identity.models import Organization, User
    from app.jobs.models import (
        Job,
        JobRequirement,
        JobVersion,
        RequirementCategory,
        RequirementImportance,
    )

    org = Organization(name="Org A", slug="org-a")
    user = User(email="owner-a@example.test", password_hash="synthetic-hash", name="Owner A")
    db.add_all([org, user])
    db.flush()
    job = Job(organization_id=org.id, title="Synthetic role", owner_id=user.id)
    db.add(job)
    db.flush()
    db.add_all(
        [
            JobRequirement(
                job_id=job.id,
                category=RequirementCategory.SKILL,
                description="Synthetic skill",
                importance=RequirementImportance.DESIRABLE,
            ),
            JobVersion(job_id=job.id, version=1, snapshot={"job": {}}),
        ]
    )
    db.flush()

    db.delete(job)
    db.flush()

    assert db.scalars(select(JobRequirement)).all() == []
    assert db.scalars(select(JobVersion)).all() == []
