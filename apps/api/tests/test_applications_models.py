from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

# Registrar tablas al importar: `test_auth` recarga `app.db.base` al terminar y
# los modelos importados después quedarían en una metadata distinta de `Base`.
import app.applications.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.applications.models import Application, ApplicationSource, ApplicationStage, StageChange
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


def _seed_relations(db: DBSession) -> tuple[object, object]:
    from app.candidates.models import Candidate
    from app.identity.models import Organization, User
    from app.jobs.models import Job

    org = Organization(name="Org A", slug="org-a")
    user = User(email="owner-a@example.test", password_hash="synthetic-hash", name="Owner A")
    db.add_all([org, user])
    db.flush()
    job = Job(organization_id=org.id, title="Synthetic role", owner_id=user.id)
    candidate = Candidate(
        organization_id=org.id,
        name="Synthetic Candidate",
        email="candidate@example.test",
    )
    db.add_all([job, candidate])
    db.flush()
    return job, candidate


def test_pipeline_enums_use_declared_values() -> None:
    assert [stage.value for stage in ApplicationStage] == [
        "applied",
        "screening",
        "interview",
        "offer",
        "hired",
        "rejected",
    ]
    assert [source.value for source in ApplicationSource] == [
        "manual",
        "import",
        "referral",
        "careers",
    ]


def test_application_starts_applied_with_utc_timestamps(db: DBSession) -> None:
    job, candidate = _seed_relations(db)
    from app.identity.models import Organization

    org = db.scalars(select(Organization)).one()
    application = Application(
        organization_id=org.id,
        job_id=job.id,  # type: ignore[attr-defined]
        candidate_id=candidate.id,  # type: ignore[attr-defined]
    )
    db.add(application)
    db.flush()

    assert application.stage is ApplicationStage.APPLIED
    assert application.source is None
    assert application.created_at.utcoffset() == timedelta(0)
    assert application.updated_at.utcoffset() == timedelta(0)


def test_duplicate_application_per_job_and_candidate_is_rejected(db: DBSession) -> None:
    job, candidate = _seed_relations(db)
    from app.identity.models import Organization

    org = db.scalars(select(Organization)).one()
    application = Application(
        organization_id=org.id,
        job_id=job.id,  # type: ignore[attr-defined]
        candidate_id=candidate.id,  # type: ignore[attr-defined]
    )
    db.add(application)
    db.flush()

    _reject_flush(
        db,
        Application(
            organization_id=org.id,
            job_id=job.id,  # type: ignore[attr-defined]
            candidate_id=candidate.id,  # type: ignore[attr-defined]
        ),
    )
    assert len(db.scalars(select(Application)).all()) == 1


def test_stage_change_has_nullable_origin_and_cascades_with_application(
    db: DBSession,
) -> None:
    job, candidate = _seed_relations(db)
    from app.identity.models import Organization

    org = db.scalars(select(Organization)).one()
    application = Application(
        organization_id=org.id,
        job_id=job.id,  # type: ignore[attr-defined]
        candidate_id=candidate.id,  # type: ignore[attr-defined]
    )
    db.add(application)
    db.flush()
    change = StageChange(
        application_id=application.id,
        from_stage=None,
        to_stage=ApplicationStage.APPLIED,
    )
    db.add(change)
    db.flush()

    assert change.from_stage is None
    assert change.actor_id is None
    assert change.note is None
    assert change.created_at.utcoffset() == timedelta(0)

    db.delete(application)
    db.flush()
    assert db.scalars(select(StageChange)).all() == []


def test_pipeline_indexes_exist_for_tenant_job_candidate_and_stage(engine: Engine) -> None:
    applications = {
        index["name"] for index in inspect(engine).get_indexes("applications")
    }
    changes = {index["name"] for index in inspect(engine).get_indexes("stage_changes")}

    assert {
        "ix_applications_organization_id",
        "ix_applications_job_id",
        "ix_applications_candidate_id",
        "ix_applications_stage",
    } <= applications
    assert "ix_stage_changes_application_id" in changes


def test_application_contract_has_no_protected_candidate_attributes() -> None:
    protected = {
        "age",
        "birth_date",
        "date_of_birth",
        "disability",
        "gender",
        "marital_status",
        "nationality",
        "photo",
        "religion",
    }
    columns = set(Application.__table__.columns.keys()) | set(
        StageChange.__table__.columns.keys()
    )
    assert not protected & columns
