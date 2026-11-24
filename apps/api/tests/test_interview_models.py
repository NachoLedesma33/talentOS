from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

import app.identity.models  # noqa: F401
from app.agents.models import UnsafeAgentPayloadError
from app.applications.models import Application
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Organization, User
from app.interviews.models import (
    InterviewDomainError,
    InterviewFeedback,
    InterviewFeedbackStatus,
    InterviewGuide,
    InterviewGuideRevision,
    InterviewGuideStatus,
    InterviewQuestion,
    InterviewQuestionCategory,
    InterviewQuestionStatus,
    InterviewTenantMismatchError,
    InvalidInterviewTransitionError,
)
from app.interviews.repositories import (
    get_feedback,
    get_guide,
    get_question,
    get_revision,
    list_feedback,
    list_guides,
    list_questions,
    list_revisions,
    next_version,
    save_revision,
)
from app.interviews.schemas import (
    GuideRevisionCreate,
    InterviewFeedbackCreate,
    InterviewFeedbackUpdate,
    InterviewGuideCreate,
    InterviewGuideUpdate,
    InterviewQuestionCreate,
    InterviewQuestionUpdate,
)
from app.jobs.models import Job

_INTERVIEW_TABLES = {
    "interview_guides",
    "interview_guide_revisions",
    "interview_questions",
    "interview_feedbacks",
}
_FORBIDDEN_FIELDS = frozenset(
    {
        "age",
        "decision",
        "ethnicity",
        "gender",
        "health",
        "hire_decision",
        "hiring_decision",
        "nationality",
        "personality",
        "rating",
        "religion",
        "score",
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


def _seed(
    db: DBSession,
) -> tuple[Organization, Organization, User, User, Application, Application]:
    org_a = Organization(name="Org A", slug="interviews-org-a")
    org_b = Organization(name="Org B", slug="interviews-org-b")
    user_a = User(
        email="owner-a-interviews@example.test", password_hash="synthetic-hash", name="Synthetic A"
    )
    user_b = User(
        email="owner-b-interviews@example.test", password_hash="synthetic-hash", name="Synthetic B"
    )
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()

    job_a = Job(organization_id=org_a.id, title="Synthetic role A", owner_id=user_a.id)
    job_b = Job(organization_id=org_b.id, title="Synthetic role B", owner_id=user_b.id)
    candidate_a = Candidate(
        organization_id=org_a.id,
        name="Synthetic Candidate A",
        email="candidate-a-interviews@example.test",
    )
    candidate_b = Candidate(
        organization_id=org_b.id,
        name="Synthetic Candidate B",
        email="candidate-b-interviews@example.test",
    )
    db.add_all([job_a, job_b, candidate_a, candidate_b])
    db.flush()

    application_a = Application(
        organization_id=org_a.id, job_id=job_a.id, candidate_id=candidate_a.id
    )
    application_b = Application(
        organization_id=org_b.id, job_id=job_b.id, candidate_id=candidate_b.id
    )
    db.add_all([application_a, application_b])
    db.flush()
    return org_a, org_b, user_a, user_b, application_a, application_b


def _guide(
    org: Organization,
    application: Application,
    user: User,
    *,
    version: int = 1,
    status: InterviewGuideStatus = InterviewGuideStatus.DRAFT,
    title: str = "Synthetic guide",
) -> InterviewGuide:
    return InterviewGuide(
        organization_id=org.id,
        application_id=application.id,
        version=version,
        status=status,
        title=title,
        created_by=user.id,
    )


def _question(
    guide: InterviewGuide,
    org: Organization,
    user: User,
    *,
    position: int = 1,
    requirement_id: uuid.UUID | None = None,
    category: InterviewQuestionCategory = InterviewQuestionCategory.TECHNICAL,
) -> InterviewQuestion:
    return InterviewQuestion(
        organization_id=org.id,
        guide_id=guide.id,
        requirement_id=requirement_id or uuid.uuid4(),
        position=position,
        category=category,
        question="¿Cómo abordó un problema técnico similar?",
        evidence_focus="Experiencia verificable con el requisito",
        competency="Resolución de problemas",
        model_version="mock-model-v1",
        prompt_version="interview-v1",
        created_by=user.id,
    )


def _feedback(
    guide: InterviewGuide,
    question: InterviewQuestion,
    application: Application,
    org: Organization,
    user: User,
) -> InterviewFeedback:
    return InterviewFeedback(
        organization_id=org.id,
        guide_id=guide.id,
        question_id=question.id,
        application_id=application.id,
        interviewer_id=user.id,
        observed_evidence=["Ejemplo sintético"],
        gaps=["Sin evidencia de profundización"],
    )


def test_enum_transitions_are_deterministic_and_reject_free_strings(db: DBSession) -> None:
    org_a, _, user_a, _, application_a, _ = _seed(db)
    guide = _guide(org_a, application_a, user_a)
    db.add(guide)
    db.flush()

    guide.transition_to(InterviewGuideStatus.PUBLISHED)
    guide.transition_to(InterviewGuideStatus.ARCHIVED)
    assert guide.status is InterviewGuideStatus.ARCHIVED
    assert guide.created_at.utcoffset() == timedelta(0)
    assert guide.updated_at.utcoffset() == timedelta(0)
    with pytest.raises(InvalidInterviewTransitionError):
        guide.transition_to(InterviewGuideStatus.PUBLISHED)
    with pytest.raises(InvalidInterviewTransitionError):
        _guide(org_a, application_a, user_a).transition_to(
            cast(InterviewGuideStatus, "reviewed")
        )

    question = _question(guide, org_a, user_a)
    db.add(question)
    db.flush()
    question.transition_to(InterviewQuestionStatus.APPROVED)
    question.transition_to(InterviewQuestionStatus.ARCHIVED)
    assert question.status is InterviewQuestionStatus.ARCHIVED
    with pytest.raises(InvalidInterviewTransitionError):
        question.transition_to(InterviewQuestionStatus.REJECTED)
    with pytest.raises(InvalidInterviewTransitionError):
        _question(guide, org_a, user_a).transition_to(cast(InterviewQuestionStatus, "done"))

    feedback = _feedback(guide, question, application_a, org_a, user_a)
    db.add(feedback)
    db.flush()
    feedback.transition_to(InterviewFeedbackStatus.NEEDS_REVIEW)
    submitted_at = datetime.now(UTC)
    feedback.transition_to(InterviewFeedbackStatus.SUBMITTED, submitted_at)
    assert feedback.status is InterviewFeedbackStatus.SUBMITTED
    assert feedback.submitted_at == submitted_at
    with pytest.raises(InvalidInterviewTransitionError):
        feedback.transition_to(InterviewFeedbackStatus.NEEDS_REVIEW)
    pending = _feedback(guide, question, application_a, org_a, user_a)
    with pytest.raises(InvalidInterviewTransitionError):
        pending.transition_to(InterviewFeedbackStatus.SUBMITTED)
    with pytest.raises(InvalidInterviewTransitionError):
        pending.transition_to(cast(InterviewFeedbackStatus, "hired"))

    assert [item.value for item in InterviewGuideStatus] == ["draft", "published", "archived"]
    assert [item.value for item in InterviewFeedbackStatus] == [
        "pending",
        "submitted",
        "needs_review",
    ]
    assert issubclass(InvalidInterviewTransitionError, InterviewDomainError)


def test_unique_versions_positions_and_requirement_category(db: DBSession) -> None:
    org_a, _, user_a, _, application_a, _ = _seed(db)
    first = _guide(org_a, application_a, user_a)
    db.add(first)
    db.flush()

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(_guide(org_a, application_a, user_a, version=1, title="Synthetic duplicate"))
            db.flush()

    second = _guide(org_a, application_a, user_a, version=2)
    db.add(second)
    db.flush()

    requirement = uuid.uuid4()
    question = _question(first, org_a, user_a, requirement_id=requirement)
    db.add(question)
    db.flush()

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(_question(first, org_a, user_a, position=1, requirement_id=uuid.uuid4()))
            db.flush()

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                _question(
                    first,
                    org_a,
                    user_a,
                    position=2,
                    requirement_id=requirement,
                    category=InterviewQuestionCategory.TECHNICAL,
                )
            )
            db.flush()

    assert next_version(db, org_a.id, application_a.id) == 3


def test_repositories_do_not_expose_other_tenant_resources(db: DBSession) -> None:
    org_a, org_b, user_a, _, application_a, _ = _seed(db)
    guide = _guide(org_a, application_a, user_a)
    db.add(guide)
    db.flush()
    revision = save_revision(
        db,
        organization_id=org_a.id,
        guide_id=guide.id,
        version=1,
        snapshot={"topics": ["synthetic"]},
        created_by=user_a.id,
    )
    question = _question(guide, org_a, user_a)
    db.add(question)
    db.flush()
    feedback = _feedback(guide, question, application_a, org_a, user_a)
    db.add(feedback)
    db.commit()

    assert get_guide(db, org_b.id, guide.id) is None
    assert list_guides(db, org_b.id, application_id=application_a.id) == []
    assert next_version(db, org_b.id, application_a.id) == 1
    assert get_revision(db, org_b.id, guide.id, revision.version) is None
    assert list_revisions(db, org_b.id, guide.id) == []
    assert get_question(db, org_b.id, question.id) is None
    assert list_questions(db, org_b.id, guide_id=guide.id) == []
    assert get_feedback(db, org_b.id, feedback.id) is None
    assert list_feedback(db, org_b.id, guide_id=guide.id) == []

    with pytest.raises(InterviewTenantMismatchError):
        save_revision(
            db,
            organization_id=org_b.id,
            guide_id=guide.id,
            version=2,
            snapshot={"topics": ["synthetic"]},
            created_by=user_a.id,
        )

    assert get_guide(db, org_a.id, guide.id) is not None
    assert get_question(db, org_a.id, question.id) is not None
    assert get_feedback(db, org_a.id, feedback.id) is not None


def test_snapshot_validator_rejects_cv_secrets_and_extra_fields(db: DBSession) -> None:
    org_a, _, user_a, _, application_a, _ = _seed(db)
    guide = _guide(org_a, application_a, user_a)
    db.add(guide)
    db.flush()

    for unsafe in (
        {"api_key": "synthetic-value"},
        {"cv_text": "Synthetic resume"},
        {"chain_of_thought": "hidden"},
        {"note": "Bearer synthetic-token"},
    ):
        with pytest.raises(ValidationError):
            GuideRevisionCreate.model_validate({"version": 1, "snapshot": unsafe})

    with pytest.raises(ValidationError):
        GuideRevisionCreate.model_validate(
            {
                "version": 1,
                "snapshot": {"topics": ["synthetic"]},
                "organization_id": str(org_a.id),
            }
        )

    contract = GuideRevisionCreate.model_validate(
        {"version": 1, "snapshot": {"requirement_id": str(uuid.uuid4()), "topics": ["python"]}}
    )
    with pytest.raises(UnsafeAgentPayloadError):
        save_revision(
            db,
            organization_id=org_a.id,
            guide_id=guide.id,
            version=1,
            snapshot={"secret": "synthetic"},
            created_by=user_a.id,
        )

    saved = save_revision(
        db,
        organization_id=org_a.id,
        guide_id=guide.id,
        version=1,
        snapshot=contract.snapshot,
        created_by=user_a.id,
    )
    assert saved.snapshot["topics"] == ["python"]
    assert "secret" not in str(saved.snapshot)


def test_feedback_has_no_score_or_hiring_decision() -> None:
    model_columns = set().union(
        *(set(model.__table__.columns.keys()) for model in (
            InterviewGuide,
            InterviewGuideRevision,
            InterviewQuestion,
            InterviewFeedback,
        ))
    )
    contract_fields = set().union(
        *(set(model.model_fields) for model in (
            InterviewGuideCreate,
            InterviewGuideUpdate,
            InterviewQuestionCreate,
            InterviewQuestionUpdate,
            InterviewFeedbackCreate,
            InterviewFeedbackUpdate,
            GuideRevisionCreate,
        ))
    )
    assert not _FORBIDDEN_FIELDS & (model_columns | contract_fields)
    assert "organization_id" in model_columns
    assert "organization_id" not in contract_fields
    assert {
        "observed_evidence",
        "gaps",
        "follow_up_needed",
        "notes",
        "submitted_at",
    } <= set(InterviewFeedback.__table__.columns.keys())
    assert "requirement_id" in InterviewQuestion.__table__.columns
    assert not InterviewQuestion.__table__.c.requirement_id.foreign_keys
    with pytest.raises(ValidationError):
        InterviewFeedbackUpdate.model_validate(
            {"notes": "Synthetic", "organization_id": str(uuid.uuid4())}
        )
    with pytest.raises(ValidationError):
        InterviewFeedbackUpdate.model_validate({"score": 5})
    with pytest.raises(ValidationError):
        InterviewGuideCreate.model_validate(
            {"application_id": str(uuid.uuid4()), "title": "x", "organization_id": "x"}
        )


def test_revision_history_is_queryable_by_version(db: DBSession) -> None:
    org_a, _, user_a, _, application_a, _ = _seed(db)
    guide = _guide(org_a, application_a, user_a)
    db.add(guide)
    db.flush()

    for version in (3, 1, 2):
        save_revision(
            db,
            organization_id=org_a.id,
            guide_id=guide.id,
            version=version,
            snapshot={"version": version, "topics": ["synthetic"]},
            created_by=user_a.id,
        )
    history = list_revisions(db, org_a.id, guide.id)
    assert [item.version for item in history] == [1, 2, 3]
    second = get_revision(db, org_a.id, guide.id, 2)
    assert second is not None
    assert second.snapshot == {"version": 2, "topics": ["synthetic"]}
    assert get_revision(db, org_a.id, guide.id, 4) is None


def test_interview_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-interviews.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    # `test_auth` recarga `app.db.base`; env.py debe ver el Base con modelos registrados.
    monkeypatch.setattr("app.db.base.Base", Base, raising=True)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0010_agent_runtime")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert not _INTERVIEW_TABLES & before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert _INTERVIEW_TABLES <= after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0010_agent_runtime")
        reverted = set(inspect(engine).get_table_names())
        assert not _INTERVIEW_TABLES & reverted
    finally:
        engine.dispose()
