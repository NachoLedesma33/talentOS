from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

from app.agents.contracts import (
    WORKSPACE_ASSISTANT_WORKFLOW,
    AssistantActionType,
    AssistantFormId,
    AssistantSurface,
)
from app.agents.models import AgentEvent, AgentRun, Approval
from app.agents.repositories import get_or_create_agent_run, list_agent_events
from app.agents.tools import (
    ToolContext,
    ToolErrorCode,
    ToolInvocationError,
    ToolRegistry,
    build_assistant_registry,
)
from app.applications.models import Application, ApplicationStage
from app.automation.models import Automation
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Membership, MembershipRole, Organization, User, UserStatus
from app.jobs.models import Job, JobStatus


@dataclass(frozen=True)
class Seed:
    org_a: Organization
    org_b: Organization
    owner_a: User
    viewer_a: User
    owner_b: User
    run_a: AgentRun
    run_b: AgentRun
    job_a: Job
    job_b: Job
    candidate_a: Candidate
    candidate_b: Candidate
    automation_a: Automation
    automation_b: Automation


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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


@pytest.fixture
def seed(db: DBSession) -> Seed:
    org_a = Organization(name="Assistant Org A", slug="assistant-org-a")
    org_b = Organization(name="Assistant Org B", slug="assistant-org-b")
    owner_a = User(
        email="assistant-owner@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Owner",
        status=UserStatus.ACTIVE,
    )
    viewer_a = User(
        email="assistant-viewer@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Viewer",
        status=UserStatus.ACTIVE,
    )
    owner_b = User(
        email="assistant-foreign@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Foreign",
        status=UserStatus.ACTIVE,
    )
    db.add_all([org_a, org_b, owner_a, viewer_a, owner_b])
    db.flush()
    db.add_all(
        [
            Membership(organization_id=org_a.id, user_id=owner_a.id, role=MembershipRole.OWNER),
            Membership(organization_id=org_a.id, user_id=viewer_a.id, role=MembershipRole.VIEWER),
            Membership(organization_id=org_b.id, user_id=owner_b.id, role=MembershipRole.OWNER),
        ]
    )
    run_a = get_or_create_agent_run(
        db,
        organization_id=org_a.id,
        workflow=WORKSPACE_ASSISTANT_WORKFLOW.workflow,
        version=WORKSPACE_ASSISTANT_WORKFLOW.version,
        idempotency_key="assistant-run-a",
        correlation_id=uuid.uuid4(),
        actor_id=owner_a.id,
    )
    run_b = get_or_create_agent_run(
        db,
        organization_id=org_b.id,
        workflow=WORKSPACE_ASSISTANT_WORKFLOW.workflow,
        version=WORKSPACE_ASSISTANT_WORKFLOW.version,
        idempotency_key="assistant-run-b",
        correlation_id=uuid.uuid4(),
        actor_id=owner_b.id,
    )
    job_a = Job(
        organization_id=org_a.id,
        owner_id=owner_a.id,
        title="Analista de selección · demo",
        description="Synthetic job",
        status=JobStatus.OPEN,
    )
    job_b = Job(
        organization_id=org_b.id,
        owner_id=owner_b.id,
        title="Foreign Job",
        description="Synthetic foreign job",
        status=JobStatus.OPEN,
    )
    candidate_a = Candidate(
        organization_id=org_a.id,
        name="Synthetic Candidate",
        email="assistant-candidate@example.test",
    )
    candidate_b = Candidate(
        organization_id=org_b.id,
        name="Foreign Candidate",
        email="assistant-foreign-candidate@example.test",
    )
    db.add_all([job_a, job_b, candidate_a, candidate_b])
    db.flush()
    db.add(
        Application(
            organization_id=org_a.id,
            job_id=job_a.id,
            candidate_id=candidate_a.id,
            stage=ApplicationStage.APPLIED,
        )
    )
    automation_a = Automation(
        organization_id=org_a.id,
        name="Draft automation",
        created_by=owner_a.id,
    )
    automation_b = Automation(
        organization_id=org_b.id,
        name="Foreign automation",
        created_by=owner_b.id,
    )
    db.add_all([automation_a, automation_b])
    db.flush()
    return Seed(
        org_a=org_a,
        org_b=org_b,
        owner_a=owner_a,
        viewer_a=viewer_a,
        owner_b=owner_b,
        run_a=run_a,
        run_b=run_b,
        job_a=job_a,
        job_b=job_b,
        candidate_a=candidate_a,
        candidate_b=candidate_b,
        automation_a=automation_a,
        automation_b=automation_b,
    )


@pytest.fixture
def registry() -> ToolRegistry:
    return build_assistant_registry()


def _ctx(
    db: DBSession,
    data: Seed,
    *,
    role: MembershipRole = MembershipRole.OWNER,
    actor_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    run: AgentRun | None = None,
    idempotency_key: str = "assistant-tools-idem",
) -> ToolContext:
    return ToolContext(
        db=db,
        organization_id=organization_id or data.org_a.id,
        actor_id=actor_id or data.owner_a.id,
        actor_role=role,
        agent_run_id=(run or data.run_a).id,
        correlation_id=uuid.uuid4(),
        idempotency_key=idempotency_key,
    )


def test_assistant_registry_is_read_only_and_closed(registry: ToolRegistry) -> None:
    names = set(registry.names())

    assert names <= set(WORKSPACE_ASSISTANT_WORKFLOW.allowed_tools)
    assert "get_platform_capabilities" in names
    assert "create_message_draft" not in names
    assert "request_human_approval" not in names
    for name in names:
        definition = registry.get(name)
        assert definition.is_write is False
        assert definition.allowed_workflows == frozenset({WORKSPACE_ASSISTANT_WORKFLOW.workflow})
        assert MembershipRole.VIEWER in definition.roles


def test_capabilities_and_forms_are_closed(
    db: DBSession, seed: Seed, registry: ToolRegistry
) -> None:
    ctx = _ctx(db, seed, role=MembershipRole.VIEWER, actor_id=seed.viewer_a.id)

    capabilities = registry.invoke(ctx, "get_platform_capabilities", {})

    assert capabilities.workflow == "workspace_assistant"
    assert capabilities.version == "1.0.0"
    assert set(capabilities.intents) == {intent.value for intent in AssistantActionType}
    assert set(capabilities.surfaces) == {surface.value for surface in AssistantSurface}
    assert set(capabilities.forms) == {form.value for form in AssistantFormId}
    assert capabilities.routes and all(route.startswith("/") for route in capabilities.routes)
    assert all("://" not in route for route in capabilities.routes)

    schema = registry.invoke(ctx, "get_form_schema", {"form_id": "candidate.create"})

    assert [field.name for field in schema.fields] == ["name", "location"]
    assert all(field.sensitive is False for field in schema.fields)
    with pytest.raises(ToolInvocationError) as exc:
        registry.invoke(ctx, "get_form_schema", {"form_id": "candidate.create", "email": "x"})
    assert exc.value.code is ToolErrorCode.INVALID_INPUT


def test_workspace_lists_are_tenant_scoped(
    db: DBSession, seed: Seed, registry: ToolRegistry
) -> None:
    ctx = _ctx(db, seed)

    summary = registry.invoke(ctx, "get_workspace_summary", {})
    jobs = registry.invoke(ctx, "list_jobs", {"limit": 10})
    candidates = registry.invoke(ctx, "list_candidates", {})
    applications = registry.invoke(ctx, "list_applications", {})

    assert summary.jobs == 1
    assert summary.candidates == 1
    assert summary.applications == 1
    assert summary.documents == 0
    assert [item.job_id for item in jobs.jobs] == [seed.job_a.id]
    assert [item.candidate_id for item in candidates.candidates] == [seed.candidate_a.id]
    assert [item.application_id for item in applications.applications] != []

    foreign_ctx = _ctx(
        db,
        seed,
        role=MembershipRole.OWNER,
        actor_id=seed.owner_b.id,
        organization_id=seed.org_b.id,
        run=seed.run_b,
    )
    foreign_jobs = registry.invoke(foreign_ctx, "list_jobs", {})
    assert [item.job_id for item in foreign_jobs.jobs] == [seed.job_b.id]


def test_foreign_resource_ids_are_not_available(
    db: DBSession, seed: Seed, registry: ToolRegistry
) -> None:
    ctx = _ctx(db, seed)

    with pytest.raises(ToolInvocationError) as exc:
        registry.invoke(
            ctx,
            "get_automation_status",
            {"automation_id": str(seed.automation_b.id)},
        )
    assert exc.value.code is ToolErrorCode.TENANT_MISMATCH

    with pytest.raises(ToolInvocationError) as exc:
        registry.invoke(
            ctx,
            "get_candidate_profile",
            {"candidate_id": str(seed.candidate_b.id)},
        )
    assert exc.value.code is ToolErrorCode.TENANT_MISMATCH

    status = registry.invoke(
        ctx, "get_automation_status", {"automation_id": str(seed.automation_a.id)}
    )
    assert status.automation_id == seed.automation_a.id
    assert status.status == "draft"
    assert status.recent_runs == 0


def test_viewer_reads_without_write_capability(
    db: DBSession, seed: Seed, registry: ToolRegistry
) -> None:
    ctx = _ctx(db, seed, role=MembershipRole.VIEWER, actor_id=seed.viewer_a.id)

    assert registry.invoke(ctx, "get_workspace_summary", {}).organization_id == seed.org_a.id
    with pytest.raises(ToolInvocationError) as exc:
        registry.invoke(ctx, "create_message_draft", {})
    assert exc.value.code is ToolErrorCode.UNKNOWN_TOOL


def test_quota_events_are_bounded_and_without_secrets(
    db: DBSession, seed: Seed, registry: ToolRegistry
) -> None:
    ctx = _ctx(db, seed, idempotency_key="assistant-capabilities-idem")

    for _ in range(5):
        registry.invoke(ctx, "get_platform_capabilities", {})
    with pytest.raises(ToolInvocationError) as exc:
        registry.invoke(ctx, "get_platform_capabilities", {})
    assert exc.value.code is ToolErrorCode.RATE_LIMITED

    events = list_agent_events(db, seed.org_a.id, seed.run_a.id)
    assert len(events) == 6
    hashes = {str(event.payload["idempotency_hash"]) for event in events}
    assert len(hashes) == 1
    raw = " ".join(str(event.payload) for event in events)
    for secret in ("password_hash", "synthetic-hash", "assistant-candidate@example.test"):
        assert secret not in raw
    assert db.scalar(select(AgentRun).where(AgentRun.id == seed.run_a.id)) == seed.run_a
    assert db.scalar(select(AgentEvent).where(AgentEvent.agent_run_id == seed.run_a.id)) is not None
    assert db.scalar(select(Approval).where(Approval.organization_id == seed.org_a.id)) is None
