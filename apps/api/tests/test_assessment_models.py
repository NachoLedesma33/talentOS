from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.applications.models import Application
from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)
from app.assessment.schemas import (
    AssessmentListResponse,
    AssessmentResult,
    AssessmentSummary,
    RequirementEvaluationCreate,
    ReviewDecision,
)
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Organization, User
from app.jobs.models import Job, JobVersion

_PROTECTED = frozenset(
    {
        "age",
        "birth_date",
        "commitment",
        "date_of_birth",
        "disability",
        "emotion",
        "ethnicity",
        "gender",
        "health",
        "intelligence",
        "marital_status",
        "nationality",
        "personality",
        "photo",
        "religion",
        "sexual_orientation",
    }
)


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


def _seed(db: DBSession) -> tuple[Organization, User, Application, JobVersion, Candidate]:
    org = Organization(name="Org A", slug="assessment-org-a")
    user = User(
        email="owner-assessment@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Owner",
    )
    db.add_all([org, user])
    db.flush()

    job = Job(organization_id=org.id, title="Synthetic role", owner_id=user.id)
    candidate = Candidate(
        organization_id=org.id,
        name="Synthetic Candidate",
        email="candidate-assessment@example.test",
    )
    db.add_all([job, candidate])
    db.flush()

    version = JobVersion(job_id=job.id, version=1, snapshot={"requirements": []})
    application = Application(organization_id=org.id, job_id=job.id, candidate_id=candidate.id)
    db.add_all([version, application])
    db.flush()
    return org, user, application, version, candidate


def _assessment(
    org: Organization,
    user: User,
    application: Application,
    version: JobVersion,
    candidate: Candidate,
    prompt_version: str = "matching-v1",
) -> Assessment:
    return Assessment(
        organization_id=org.id,
        application_id=application.id,
        job_version_id=version.id,
        candidate_id=candidate.id,
        created_by=user.id,
        model_version="mock-model-v1",
        prompt_version=prompt_version,
        summary={"strengths": ["Synthetic strength"], "gaps": [], "questions": []},
        limitations=["Synthetic limitation"],
    )


def _evaluation(
    assessment: Assessment,
    status: RequirementEvaluationStatus = RequirementEvaluationStatus.SUPPORTED,
) -> RequirementEvaluation:
    return RequirementEvaluation(
        assessment_id=assessment.id,
        requirement_id=uuid.uuid4(),
        status=status,
        explanation="Synthetic explanation",
        evidence=[
            {
                "document_id": str(uuid.uuid4()),
                "field_name": "skills",
                "page": 1,
                "quote": "Synthetic skill",
                "offset": 0,
            }
        ],
        limitations=["Synthetic limitation"],
    )


def test_enums_defaults_and_utc_timestamps(db: DBSession) -> None:
    org, user, application, version, candidate = _seed(db)
    assessment = _assessment(org, user, application, version, candidate)
    db.add(assessment)
    db.flush()
    evaluation = RequirementEvaluation(
        assessment_id=assessment.id,
        requirement_id=uuid.uuid4(),
        explanation="Synthetic explanation",
        evidence=[],
        limitations=[],
    )
    db.add(evaluation)
    db.flush()

    assert [item.value for item in AssessmentStatus] == [
        "pending",
        "completed",
        "failed",
        "needs_review",
    ]
    assert [item.value for item in RequirementEvaluationStatus] == [
        "supported",
        "partial",
        "not_found",
        "needs_review",
    ]
    assert assessment.status is AssessmentStatus.PENDING
    assert evaluation.status is RequirementEvaluationStatus.NEEDS_REVIEW
    assert assessment.created_at.utcoffset() == timedelta(0)
    assert assessment.updated_at.utcoffset() == timedelta(0)
    assert evaluation.created_at.utcoffset() == timedelta(0)


def test_unique_assessment_per_prompt_version(db: DBSession) -> None:
    org, user, application, version, candidate = _seed(db)
    first = _assessment(org, user, application, version, candidate, prompt_version="v1")
    db.add(first)
    db.flush()

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(_assessment(org, user, application, version, candidate, prompt_version="v1"))
            db.flush()

    second = _assessment(org, user, application, version, candidate, prompt_version="v2")
    db.add(second)
    db.flush()
    assert {item.prompt_version for item in db.scalars(select(Assessment)).all()} == {"v1", "v2"}


def test_indexes_and_unique_constraint_names(engine: Engine) -> None:
    assessments = {index["name"] for index in inspect(engine).get_indexes("assessments")}
    evaluations = {
        index["name"] for index in inspect(engine).get_indexes("requirement_evaluations")
    }

    assert {
        "ix_assessments_organization_id",
        "ix_assessments_application_id",
        "ix_assessments_candidate_id",
        "ix_assessments_status",
    } <= assessments
    assert {
        "ix_requirement_evaluations_assessment_id",
        "ix_requirement_evaluations_requirement_id",
        "ix_requirement_evaluations_status",
    } <= evaluations
    assert "uq_assessments_org_app_version_prompt" in {
        item.name for item in Assessment.__table__.constraints if item.name
    }


def test_evaluations_cascade_when_assessment_is_deleted(db: DBSession) -> None:
    org, user, application, version, candidate = _seed(db)
    assessment = _assessment(org, user, application, version, candidate)
    db.add(assessment)
    db.flush()
    db.add(_evaluation(assessment))
    db.commit()

    db.delete(assessment)
    db.commit()

    assert db.scalars(select(Assessment)).all() == []
    assert db.scalars(select(RequirementEvaluation)).all() == []


def test_evidence_json_and_review_fields(db: DBSession) -> None:
    org, user, application, version, candidate = _seed(db)
    assessment = _assessment(org, user, application, version, candidate)
    db.add(assessment)
    db.flush()
    evaluation = _evaluation(assessment, RequirementEvaluationStatus.PARTIAL)
    db.add(evaluation)
    db.commit()
    db.expire_all()

    stored = db.scalar(
        select(RequirementEvaluation).where(RequirementEvaluation.id == evaluation.id)
    )
    assert stored is not None
    assert stored.evidence[0]["field_name"] == "skills"
    assert stored.evidence[0]["offset"] == 0
    assert stored.review_required is False
    assert stored.reviewed_by is None
    assert stored.reviewed_at is None

    stored_assessment = db.scalar(select(Assessment).where(Assessment.id == assessment.id))
    assert stored_assessment is not None
    assert stored_assessment.summary["strengths"] == ["Synthetic strength"]
    assert stored_assessment.summary["gaps"] == []
    assert stored_assessment.summary["questions"] == []
    assert stored_assessment.limitations == ["Synthetic limitation"]


def test_contracts_omit_score_organization_id_and_protected_attributes() -> None:
    summary = AssessmentSummary(strengths=["Synthetic"], gaps=[], questions=[])
    assert set(summary.model_dump()) == {"strengths", "gaps", "questions"}

    contract_fields = (
        set(RequirementEvaluationCreate.model_fields)
        | set(AssessmentResult.model_fields)
        | set(AssessmentListResponse.model_fields)
        | set(ReviewDecision.model_fields)
    )
    model_columns = set(Assessment.__table__.columns.keys()) | set(
        RequirementEvaluation.__table__.columns.keys()
    )
    assert "score" not in contract_fields | model_columns
    assert "organization_id" not in contract_fields
    assert not _PROTECTED & (contract_fields | model_columns)


def test_input_schemas_strip_whitespace_and_reject_organization_id() -> None:
    decision = ReviewDecision(
        status=RequirementEvaluationStatus.NEEDS_REVIEW, explanation="  Synthetic note  "
    )
    assert decision.explanation == "Synthetic note"

    with pytest.raises(ValidationError):
        ReviewDecision.model_validate(
            {
                "status": "supported",
                "explanation": "Synthetic note",
                "organization_id": str(uuid.uuid4()),
            }
        )


def test_assessment_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-assessment.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    # env.py usa fileConfig; sin este aislamiento desactiva loggers de tests posteriores.
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0008_review")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert "assessments" not in before
        assert "requirement_evaluations" not in before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert {"assessments", "requirement_evaluations"} <= after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0008_review")
        reverted = set(inspect(engine).get_table_names())
        assert "assessments" not in reverted
        assert "requirement_evaluations" not in reverted
    finally:
        engine.dispose()
