from __future__ import annotations

import json
from collections.abc import Iterator

import email_validator
import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

from app.agents.models import AgentEvent, AgentRun, Approval, ApprovalStatus
from app.applications.models import Application
from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)
from app.automation.models import Automation, AutomationStatus, AutomationVersion
from app.candidates.models import Candidate, CandidateNote
from app.db.base import Base
from app.documents.models import (
    Document,
    DocumentExtraction,
    ExtractedField,
    ExtractedFieldStatus,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.identity.service import create_organization, register_user
from app.integrations.models import EmailApprovalStatus, EmailDraft, Integration
from app.interviews.models import InterviewGuide, InterviewGuideStatus, InterviewQuestion
from app.jobs.models import Job, JobRequirement, JobVersion
from scripts.seed_demo import DEMO_EMAIL, SUPERADMIN_EMAIL, reset_demo, seed_demo

_OTHER_EMAIL = "owner.other@example.test"
_OTHER_PASSWORD = "OtherSynthetic123"


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture
def db_session() -> Iterator[DBSession]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with DBSession(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _count(db: DBSession, model: object) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_seed_demo_is_reproducible_and_reset_only_removes_demo(db_session: DBSession) -> None:
    other_user = register_user(
        db_session, email=_OTHER_EMAIL, password=_OTHER_PASSWORD, name="Otro propietario"
    )
    other_org = create_organization(
        db_session, creator=other_user, name="Otra organización", slug="otra-org"
    )

    first = seed_demo(db_session)

    assert first["candidates"] == 5
    assert first["applications"] == 5
    assert first["requirements"] == 3
    assert first["job_versions"] == 2
    assert _count(db_session, Organization) == 2
    assert _count(db_session, Job) == 1
    assert _count(db_session, JobRequirement) == 3
    assert _count(db_session, JobVersion) == 2
    assert _count(db_session, Candidate) == 5
    assert _count(db_session, Application) == 5
    assert _count(db_session, Document) == 4
    assert _count(db_session, DocumentExtraction) == 4
    assert _count(db_session, ExtractedField) == 4
    assert _count(db_session, Assessment) == 1
    assert _count(db_session, RequirementEvaluation) == 4
    assert _count(db_session, InterviewGuide) == 1
    assert _count(db_session, InterviewQuestion) == 2
    assert _count(db_session, Integration) == 1
    assert _count(db_session, EmailDraft) == 1
    assert _count(db_session, Automation) == 1
    assert _count(db_session, AutomationVersion) == 1
    assert _count(db_session, AgentRun) == 2
    assert _count(db_session, Approval) == 2

    second = seed_demo(db_session)

    assert second["candidates"] == first["candidates"]
    assert _count(db_session, Organization) == 2
    assert _count(db_session, Candidate) == 5
    assert _count(db_session, JobVersion) == 2
    assert _count(db_session, DocumentExtraction) == 4
    assert _count(db_session, RequirementEvaluation) == 4
    assert _count(db_session, EmailDraft) == 1
    assert _count(db_session, AutomationVersion) == 1
    assert _count(db_session, AgentRun) == 2

    reset_demo(db_session)

    assert _count(db_session, Organization) == 1
    assert _count(db_session, User) == 1
    assert _count(db_session, Job) == 0
    assert _count(db_session, JobRequirement) == 0
    assert _count(db_session, JobVersion) == 0
    assert _count(db_session, Candidate) == 0
    assert _count(db_session, CandidateNote) == 0
    assert _count(db_session, Application) == 0
    assert _count(db_session, Document) == 0
    assert _count(db_session, DocumentExtraction) == 0
    assert _count(db_session, ExtractedField) == 0
    assert _count(db_session, Assessment) == 0
    assert _count(db_session, RequirementEvaluation) == 0
    assert _count(db_session, InterviewGuide) == 0
    assert _count(db_session, InterviewQuestion) == 0
    assert _count(db_session, Integration) == 0
    assert _count(db_session, EmailDraft) == 0
    assert _count(db_session, Automation) == 0
    assert _count(db_session, AutomationVersion) == 0
    assert _count(db_session, AgentRun) == 0
    assert _count(db_session, AgentEvent) == 0
    assert _count(db_session, Approval) == 0
    assert db_session.get(Organization, other_org.id) is not None


def test_seed_demo_creates_superadmin_only_when_password_env_is_set(
    monkeypatch: pytest.MonkeyPatch, db_session: DBSession
) -> None:
    password = "SyntheticSuperPass789"
    monkeypatch.setenv("TALENTOS_SUPERADMIN_PASSWORD", password)

    result = seed_demo(db_session)

    assert result["superadmin"] is True
    superadmin = db_session.scalar(select(User).where(User.email == SUPERADMIN_EMAIL))
    assert superadmin is not None
    assert superadmin.is_superadmin is True
    assert superadmin.password_hash != password
    assert password not in superadmin.password_hash
    membership = db_session.scalar(
        select(Membership).where(Membership.user_id == superadmin.id)
    )
    assert membership is not None
    assert membership.role is MembershipRole.VIEWER

    monkeypatch.delenv("TALENTOS_SUPERADMIN_PASSWORD")
    reset_demo(db_session)

    assert db_session.scalar(select(User).where(User.email == SUPERADMIN_EMAIL)) is None


def test_seed_demo_exposes_verifiable_evidence_drafts_and_decided_approvals(
    db_session: DBSession,
) -> None:
    seed_demo(db_session)
    owner = db_session.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert owner is not None

    versions = list(db_session.scalars(select(JobVersion).order_by(JobVersion.version)).all())
    assert len(versions) == 2
    assert versions[0].snapshot != versions[1].snapshot

    for document in db_session.scalars(select(Document)).all():
        extraction = db_session.scalar(
            select(DocumentExtraction).where(DocumentExtraction.document_id == document.id)
        )
        assert extraction is not None
        assert extraction.pages
        for field in db_session.scalars(
            select(ExtractedField).where(ExtractedField.extraction_id == extraction.id)
        ).all():
            for item in field.evidence:
                quote = str(item["quote"])
                assert any(quote in str(page["text"]) for page in extraction.pages)

    field_statuses = {
        field.status for field in db_session.scalars(select(ExtractedField)).all()
    }
    assert field_statuses == {
        ExtractedFieldStatus.CONFIRMED,
        ExtractedFieldStatus.CORRECTED,
        ExtractedFieldStatus.MISSING,
        ExtractedFieldStatus.NEEDS_REVIEW,
    }

    assessment = db_session.scalar(select(Assessment))
    assert assessment is not None
    assert assessment.status is AssessmentStatus.NEEDS_REVIEW
    evaluation_statuses = {
        item.status
        for item in db_session.scalars(select(RequirementEvaluation)).all()
    }
    assert evaluation_statuses == {
        RequirementEvaluationStatus.SUPPORTED,
        RequirementEvaluationStatus.PARTIAL,
        RequirementEvaluationStatus.NOT_FOUND,
        RequirementEvaluationStatus.NEEDS_REVIEW,
    }

    guide = db_session.scalar(select(InterviewGuide))
    assert guide is not None
    assert guide.status is InterviewGuideStatus.DRAFT
    assert _count(db_session, InterviewQuestion) == 2

    draft = db_session.scalar(select(EmailDraft))
    assert draft is not None
    assert draft.approval_status is EmailApprovalStatus.PENDING
    assert len(draft.body_hash) == 64
    assert DEMO_EMAIL not in draft.subject

    automation = db_session.scalar(select(Automation))
    assert automation is not None
    assert automation.status is AutomationStatus.DRAFT
    assert _count(db_session, AutomationVersion) == 1

    approvals = list(db_session.scalars(select(Approval)).all())
    assert {approval.status for approval in approvals} == {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
    }
    for approval in approvals:
        assert approval.decided_by == owner.id
        assert approval.decided_at is not None
        payload = json.dumps(approval.payload).lower()
        assert DEMO_EMAIL not in payload
        assert "password" not in payload
        assert "sk-" not in payload

    events = list(db_session.scalars(select(AgentEvent)).all())
    assert len(events) == 4
    for event in events:
        payload = json.dumps(event.payload).lower()
        assert DEMO_EMAIL not in payload
        assert "cv" not in payload
