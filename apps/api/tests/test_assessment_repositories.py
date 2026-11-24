from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession

from app.applications.models import Application
from app.assessment.models import Assessment, RequirementEvaluation, RequirementEvaluationStatus
from app.assessment.repositories import (
    count_assessments,
    get_assessment,
    get_evaluation,
    list_assessments,
    list_evaluations,
)
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Organization, User
from app.jobs.models import Job, JobVersion


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine, expire_on_commit=False) as session:
        yield session


def _seed_tenant(
    db: DBSession, suffix: str
) -> tuple[Organization, User, Application, JobVersion, Candidate]:
    org = Organization(name=f"Org {suffix}", slug=f"assessment-repo-{suffix}")
    user = User(
        email=f"owner-{suffix}@example.test",
        password_hash="synthetic-hash",
        name=f"Synthetic Owner {suffix}",
    )
    db.add_all([org, user])
    db.flush()

    job = Job(organization_id=org.id, title=f"Synthetic role {suffix}", owner_id=user.id)
    candidate = Candidate(
        organization_id=org.id,
        name=f"Synthetic Candidate {suffix}",
        email=f"candidate-{suffix}@example.test",
    )
    db.add_all([job, candidate])
    db.flush()

    version = JobVersion(job_id=job.id, version=1, snapshot={"requirements": []})
    application = Application(organization_id=org.id, job_id=job.id, candidate_id=candidate.id)
    db.add_all([version, application])
    db.flush()
    return org, user, application, version, candidate


def _assessment(
    db: DBSession,
    org: Organization,
    user: User,
    application: Application,
    version: JobVersion,
    candidate: Candidate,
    prompt_version: str,
) -> Assessment:
    assessment = Assessment(
        organization_id=org.id,
        application_id=application.id,
        job_version_id=version.id,
        candidate_id=candidate.id,
        created_by=user.id,
        model_version="mock-model-v1",
        prompt_version=prompt_version,
        summary={"strengths": [], "gaps": [], "questions": []},
        limitations=[],
    )
    db.add(assessment)
    db.flush()
    return assessment


def _evaluation(
    db: DBSession,
    assessment: Assessment,
    requirement_id: uuid.UUID | None = None,
    status: RequirementEvaluationStatus = RequirementEvaluationStatus.SUPPORTED,
) -> RequirementEvaluation:
    evaluation = RequirementEvaluation(
        assessment_id=assessment.id,
        requirement_id=requirement_id or uuid.uuid4(),
        status=status,
        explanation="Synthetic explanation",
        evidence=[],
        limitations=[],
    )
    db.add(evaluation)
    db.flush()
    return evaluation


def test_get_assessment_is_tenant_scoped(db: DBSession) -> None:
    org_a, user_a, application_a, version_a, candidate_a = _seed_tenant(db, "a")
    org_b, user_b, application_b, version_b, candidate_b = _seed_tenant(db, "b")
    own = _assessment(db, org_a, user_a, application_a, version_a, candidate_a, "v1")
    foreign = _assessment(db, org_b, user_b, application_b, version_b, candidate_b, "v1")

    assert get_assessment(db, org_a.id, own.id) is not None
    assert get_assessment(db, org_a.id, foreign.id) is None
    assert get_assessment(db, org_b.id, own.id) is None
    assert get_assessment(db, org_b.id, foreign.id) is not None


def test_list_and_count_assessments_respect_filters_and_tenant(db: DBSession) -> None:
    org_a, user_a, application_a, version_a, candidate_a = _seed_tenant(db, "a")
    org_b, user_b, application_b, version_b, candidate_b = _seed_tenant(db, "b")
    _assessment(db, org_a, user_a, application_a, version_a, candidate_a, "v1")
    _assessment(db, org_a, user_a, application_a, version_a, candidate_a, "v2")
    _assessment(db, org_b, user_b, application_b, version_b, candidate_b, "v1")

    page = list_assessments(db, org_a.id, limit=1, offset=1)
    assert len(page) == 1
    assert page[0].organization_id == org_a.id

    assert len(list_assessments(db, org_a.id, application_id=application_a.id)) == 2
    assert len(list_assessments(db, org_a.id, candidate_id=candidate_a.id)) == 2
    assert list_assessments(db, org_a.id, application_id=uuid.uuid4()) == []
    assert all(item.organization_id == org_b.id for item in list_assessments(db, org_b.id))

    assert count_assessments(db, org_a.id) == 2
    assert count_assessments(db, org_a.id, application_id=application_a.id) == 2
    assert count_assessments(db, org_b.id) == 1


def test_get_evaluation_is_tenant_scoped(db: DBSession) -> None:
    org_a, user_a, application_a, version_a, candidate_a = _seed_tenant(db, "a")
    org_b, user_b, application_b, version_b, candidate_b = _seed_tenant(db, "b")
    assessment_a = _assessment(db, org_a, user_a, application_a, version_a, candidate_a, "v1")
    assessment_b = _assessment(db, org_b, user_b, application_b, version_b, candidate_b, "v1")
    own = _evaluation(db, assessment_a)
    foreign = _evaluation(db, assessment_b)

    assert get_evaluation(db, org_a.id, own.id) is not None
    assert get_evaluation(db, org_a.id, foreign.id) is None
    assert get_evaluation(db, org_b.id, own.id) is None
    assert list_evaluations(db, org_a.id, assessment_id=assessment_b.id) == []
    assert list_evaluations(db, org_b.id, assessment_id=assessment_b.id) == [foreign]


def test_list_evaluations_filters_by_tenant_assessment_and_requirement(db: DBSession) -> None:
    org_a, user_a, application_a, version_a, candidate_a = _seed_tenant(db, "a")
    org_b, user_b, application_b, version_b, candidate_b = _seed_tenant(db, "b")
    assessment_a = _assessment(db, org_a, user_a, application_a, version_a, candidate_a, "v1")
    assessment_b = _assessment(db, org_b, user_b, application_b, version_b, candidate_b, "v1")
    shared_requirement = uuid.uuid4()
    _evaluation(db, assessment_a, shared_requirement)
    _evaluation(db, assessment_a, shared_requirement, RequirementEvaluationStatus.NOT_FOUND)
    _evaluation(db, assessment_a)
    _evaluation(db, assessment_b, shared_requirement)

    assert len(list_evaluations(db, org_a.id, assessment_id=assessment_a.id)) == 3
    assert len(list_evaluations(db, org_a.id, requirement_id=shared_requirement)) == 2
    assert len(list_evaluations(db, org_a.id, limit=2)) == 2
    assert len(list_evaluations(db, org_a.id, limit=2, offset=2)) == 1
    assert all(item.assessment_id == assessment_a.id for item in list_evaluations(db, org_a.id))
    assert all(item.assessment_id == assessment_b.id for item in list_evaluations(db, org_b.id))


def test_repositories_are_read_only(db: DBSession) -> None:
    org_a, user_a, application_a, version_a, candidate_a = _seed_tenant(db, "a")
    assessment = _assessment(db, org_a, user_a, application_a, version_a, candidate_a, "v1")
    evaluation = _evaluation(db, assessment)
    before_assessments = len(db.scalars(select(Assessment)).all())
    before_evaluations = len(db.scalars(select(RequirementEvaluation)).all())

    get_assessment(db, org_a.id, assessment.id)
    list_assessments(db, org_a.id)
    count_assessments(db, org_a.id)
    get_evaluation(db, org_a.id, evaluation.id)
    list_evaluations(db, org_a.id, assessment_id=assessment.id)

    assert len(db.scalars(select(Assessment)).all()) == before_assessments
    assert len(db.scalars(select(RequirementEvaluation)).all()) == before_evaluations
