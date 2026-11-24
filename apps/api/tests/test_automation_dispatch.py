"""Tests de integración del disparo de dominio y aprobaciones humanas."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence

import pytest
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import Session as DBSession

import app.applications.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.automation.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.applications import service as applications_service
from app.applications.models import Application, ApplicationStage, StageChange
from app.automation import service as automation_service
from app.automation.models import (
    Automation,
    AutomationActionType,
    AutomationApprovalStatus,
    AutomationRunEventType,
    AutomationRunStatus,
    AutomationTenantMismatchError,
)
from app.automation.schemas import AutomationVersionCreate
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Membership, MembershipRole, Organization, User
from app.jobs.models import Job, JobStatus


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[DBSession]:
    with DBSession(db_engine, expire_on_commit=False) as session:
        yield session


class Seed:
    def __init__(
        self,
        org: Organization,
        other_org: Organization,
        owner: User,
        candidate: Candidate,
        job: Job,
        application: Application,
        change: StageChange,
    ) -> None:
        self.org = org
        self.other_org = other_org
        self.owner = owner
        self.candidate = candidate
        self.job = job
        self.application = application
        self.change = change


def _seed(db: DBSession, suffix: str = "a") -> Seed:
    org = Organization(name=f"Org Dispatch {suffix}", slug=f"dispatch-org-{suffix}")
    other_org = Organization(name=f"Org Other {suffix}", slug=f"dispatch-other-{suffix}")
    owner = User(
        email=f"owner-dispatch-{suffix}@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Owner",
    )
    db.add_all([org, other_org, owner])
    db.flush()
    db.add(
        Membership(organization_id=org.id, user_id=owner.id, role=MembershipRole.OWNER)
    )
    candidate = Candidate(
        organization_id=org.id,
        name="Synthetic Candidate",
        email=f"candidate-dispatch-{suffix}@example.test",
    )
    job = Job(
        organization_id=org.id,
        owner_id=owner.id,
        title="Synthetic role",
        description="",
        status=JobStatus.OPEN,
    )
    db.add_all([candidate, job])
    db.flush()
    application = Application(
        organization_id=org.id,
        job_id=job.id,
        candidate_id=candidate.id,
        stage=ApplicationStage.SCREENING,
    )
    db.add(application)
    db.flush()
    change = StageChange(
        application_id=application.id,
        from_stage=None,
        to_stage=ApplicationStage.SCREENING,
        actor_id=owner.id,
    )
    db.add(change)
    db.commit()
    return Seed(org, other_org, owner, candidate, job, application, change)


def _snapshot(
    *,
    conditions: Sequence[Mapping[str, object]] | None = None,
    actions: Sequence[Mapping[str, object]] | None = None,
) -> AutomationVersionCreate:
    return AutomationVersionCreate.model_validate(
        {
            "trigger": {"event_type": "application.stage_changed"},
            "conditions": list(conditions or []),
            "actions": list(actions or [{"type": "record_note"}]),
        }
    )


def _rule(
    db: DBSession,
    seed: Seed,
    *,
    conditions: Sequence[Mapping[str, object]] | None = None,
    actions: Sequence[Mapping[str, object]] | None = None,
    name: str = "Synthetic dispatch rule",
) -> Automation:
    rule = automation_service.create_automation(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        name=name,
        version=_snapshot(conditions=conditions, actions=actions),
    )
    return automation_service.activate_automation(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        automation_id=rule.id,
    )


def _runs(db: DBSession, seed: Seed, rule: Automation) -> list[object]:
    return automation_service.list_runs(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        automation_id=rule.id,
    )


def _approvals(db: DBSession, seed: Seed, run_id: uuid.UUID) -> list[object]:
    return automation_service.list_approvals(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        run_id=run_id,
    )


def test_stage_change_creates_scoped_draft_and_pending_approval(db: DBSession) -> None:
    seed = _seed(db)
    rule = _rule(
        db,
        seed,
        conditions=[
            {"field": "to_stage", "operator": "eq", "value": "interview"},
            {"field": "job_status", "operator": "eq", "value": "open"},
        ],
        actions=[{"type": "create_message_draft", "payload": {"template_id": "scheduling"}}],
    )
    change = applications_service.change_stage(
        db,
        organization_id=seed.org.id,
        application_id=seed.application.id,
        to_stage=ApplicationStage.INTERVIEW,
        actor_id=seed.owner.id,
    )
    assert change.to_stage is ApplicationStage.INTERVIEW

    runs = _runs(db, seed, rule)
    assert len(runs) == 1
    run = runs[0]
    assert run.status is AutomationRunStatus.WAITING_APPROVAL
    approvals = _approvals(db, seed, run.id)
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.action_type is AutomationActionType.CREATE_MESSAGE_DRAFT
    assert approval.status is AutomationApprovalStatus.PENDING
    payload = approval.payload
    assert payload["kind"] == "message_draft"
    assert "to" not in payload
    assert "email" not in payload
    assert "cv" not in payload
    events = automation_service.list_run_events(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        run_id=run.id,
    )
    types = [item.event_type for item in events]
    assert AutomationRunEventType.APPROVAL_REQUESTED in types
    assert AutomationRunEventType.ACTION_EXECUTED not in types


def test_approval_applies_effect_and_rejection_has_none(db: DBSession) -> None:
    seed = _seed(db, "approve")
    rule = _rule(
        db,
        seed,
        actions=[
            {"type": "propose_stage_change", "payload": {"target_stage": "offer"}}
        ],
    )
    applications_service.change_stage(
        db,
        organization_id=seed.org.id,
        application_id=seed.application.id,
        to_stage=ApplicationStage.INTERVIEW,
        actor_id=seed.owner.id,
    )
    run = _runs(db, seed, rule)[0]
    approval = _approvals(db, seed, run.id)[0]
    decided = automation_service.decide_approval(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        approval_id=approval.id,
        decision=AutomationApprovalStatus.APPROVED,
    )
    assert decided.status is AutomationApprovalStatus.APPROVED
    assert decided.decided_by == seed.owner.id
    assert decided.decided_at is not None
    db.refresh(seed.application)
    assert seed.application.stage is ApplicationStage.OFFER
    assert run.status is AutomationRunStatus.COMPLETED

    other = _seed(db, "reject")
    other_rule = _rule(
        db,
        other,
        name="Synthetic reject rule",
        actions=[
            {"type": "propose_stage_change", "payload": {"target_stage": "offer"}}
        ],
    )
    applications_service.change_stage(
        db,
        organization_id=other.org.id,
        application_id=other.application.id,
        to_stage=ApplicationStage.INTERVIEW,
        actor_id=other.owner.id,
    )
    other_run = _runs(db, other, other_rule)[0]
    other_approval = _approvals(db, other, other_run.id)[0]
    rejected = automation_service.decide_approval(
        db,
        organization_id=other.org.id,
        actor_id=other.owner.id,
        actor_role=MembershipRole.OWNER,
        approval_id=other_approval.id,
        decision=AutomationApprovalStatus.REJECTED,
    )
    assert rejected.status is AutomationApprovalStatus.REJECTED
    assert other_run.status is AutomationRunStatus.CANCELLED
    db.refresh(other.application)
    assert other.application.stage is ApplicationStage.INTERVIEW
    assert (
        db.scalar(
            select(func.count())
            .select_from(StageChange)
            .where(
                StageChange.application_id == other.application.id,
                StageChange.to_stage == ApplicationStage.OFFER,
            )
        )
        == 0
    )


def test_key_and_event_idempotency_do_not_duplicate_runs(db: DBSession) -> None:
    seed = _seed(db, "idem")
    rule = _rule(db, seed)
    kwargs = dict(
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        automation_id=rule.id,
        application_id=seed.application.id,
    )
    first = automation_service.test_automation(
        db, idempotency_key="idem-key", **kwargs
    )
    second = automation_service.test_automation(
        db, idempotency_key="idem-key", **kwargs
    )
    assert first.id == second.id
    assert len(_runs(db, seed, rule)) == 1

    change = applications_service.change_stage(
        db,
        organization_id=seed.org.id,
        application_id=seed.application.id,
        to_stage=ApplicationStage.INTERVIEW,
        actor_id=seed.owner.id,
    )
    before = len(_runs(db, seed, rule))
    for _ in range(2):
        automation_service.dispatch_domain_event(
            db,
            organization_id=seed.org.id,
            actor_id=seed.owner.id,
            actor_role=MembershipRole.OWNER,
            trigger_event_id=change.id,
        )
    assert len(_runs(db, seed, rule)) == before


def test_cross_tenant_operations_fail_before_reading_resource(db: DBSession) -> None:
    seed = _seed(db, "tenant")
    rule = _rule(db, seed)
    wrong = seed.other_org.id
    owner = seed.owner
    with pytest.raises(AutomationTenantMismatchError):
        automation_service.create_automation(
            db,
            organization_id=wrong,
            actor_id=owner.id,
            actor_role=MembershipRole.OWNER,
            name="Cross tenant",
            version=_snapshot(),
        )
    kwargs = dict(
        organization_id=wrong,
        actor_id=owner.id,
        actor_role=MembershipRole.OWNER,
        automation_id=rule.id,
        application_id=seed.application.id,
    )
    with pytest.raises(AutomationTenantMismatchError):
        automation_service.test_automation(
            db, **kwargs, idempotency_key="cross-test"
        )
    with pytest.raises(AutomationTenantMismatchError):
        automation_service.run_manual(db, **kwargs, idempotency_key="cross-run")

    run = automation_service.run_manual(
        db,
        organization_id=seed.org.id,
        actor_id=owner.id,
        actor_role=MembershipRole.OWNER,
        automation_id=rule.id,
        idempotency_key="cross-approval",
        application_id=seed.application.id,
    )
    with pytest.raises(AutomationTenantMismatchError):
        automation_service.decide_approval(
            db,
            organization_id=wrong,
            actor_id=owner.id,
            actor_role=MembershipRole.OWNER,
            approval_id=uuid.uuid4(),
            decision=AutomationApprovalStatus.APPROVED,
        )
    with pytest.raises(AutomationTenantMismatchError):
        automation_service.dispatch_domain_event(
            db,
            organization_id=wrong,
            actor_id=owner.id,
            actor_role=MembershipRole.OWNER,
            trigger_event_id=seed.change.id,
        )
    assert run.status is AutomationRunStatus.COMPLETED

    foreign_user = User(
        email="owner-foreign@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Foreign",
    )
    db.add(foreign_user)
    db.flush()
    db.add(
        Membership(
            organization_id=wrong,
            user_id=foreign_user.id,
            role=MembershipRole.OWNER,
        )
    )
    foreign_rule = automation_service.create_automation(
        db,
        organization_id=wrong,
        actor_id=foreign_user.id,
        actor_role=MembershipRole.OWNER,
        name="Foreign rule",
        version=_snapshot(),
    )
    with pytest.raises(automation_service.AutomationServiceError):
        automation_service.add_version(
            db,
            organization_id=seed.org.id,
            actor_id=owner.id,
            actor_role=MembershipRole.OWNER,
            automation_id=foreign_rule.id,
            version=_snapshot(),
        )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Automation)
            .where(Automation.organization_id == seed.org.id)
        )
        == 1
    )


def test_automation_stage_change_does_not_dispatch_again(db: DBSession) -> None:
    seed = _seed(db, "cycle")
    rule = _rule(
        db,
        seed,
        actions=[
            {"type": "propose_stage_change", "payload": {"target_stage": "offer"}}
        ],
    )
    applications_service.change_stage(
        db,
        organization_id=seed.org.id,
        application_id=seed.application.id,
        to_stage=ApplicationStage.INTERVIEW,
        actor_id=seed.owner.id,
    )
    assert len(_runs(db, seed, rule)) == 1
    approval = _approvals(db, seed, _runs(db, seed, rule)[0].id)[0]
    automation_service.decide_approval(
        db,
        organization_id=seed.org.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        approval_id=approval.id,
        decision=AutomationApprovalStatus.APPROVED,
    )
    assert len(_runs(db, seed, rule)) == 1
    # Una inicial, la del cambio a interview y la aplicada por la aprobación.
    assert (
        db.scalar(
            select(func.count())
            .select_from(StageChange)
            .where(StageChange.application_id == seed.application.id)
        )
        == 3
    )
