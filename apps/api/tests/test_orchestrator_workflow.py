from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi.testclient import TestClient
from langgraph.types import interrupt as real_interrupt
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.audit.models  # noqa: F401
import app.documents.models  # noqa: F401
from app.agents import orchestrator, service
from app.agents import tasks as agents_tasks
from app.agents.checkpoints import SQLAgentCheckpointSaver
from app.agents.contracts import (
    MATCHING_REVIEW_WORKFLOW,
    RECRUITMENT_ORCHESTRATION_WORKFLOW,
    OrchestrationNode,
)
from app.agents.matching_analyst import PROMPT_VERSION as MATCHING_PROMPT_VERSION
from app.agents.models import (
    AgentCheckpoint,
    AgentDomainError,
    AgentRun,
    AgentRunStatus,
    ApprovalStatus,
)
from app.agents.repositories import create_approval
from app.agents.schemas import validate_safe_payload
from app.applications.models import Application, ApplicationStage
from app.assessment.models import Assessment, AssessmentStatus, RequirementEvaluationStatus
from app.audit.models import AuditLog
from app.candidates.models import Candidate
from app.db.base import Base
from app.db.session import get_db
from app.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
    ExtractedField,
    ExtractedFieldName,
    ExtractedFieldStatus,
    ExtractionStatus,
)
from app.identity.dependencies import (
    get_current_organization,
    get_current_user,
    verify_origin,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.interviews.models import InterviewGuide, InterviewGuideStatus
from app.interviews.repositories import count_guides
from app.jobs.models import Job, JobStatus, JobVersion
from app.main import app as fastapi_app

_URL = "/api/v1/agents"
_QUOTE = "Skills: Python confirmed"
_CV_MARKER = "SyntheticCvMarkerOrchestrator"
_SECRET_MARKER = "SyntheticSecretMarkerOrchestrator"


@dataclass(frozen=True)
class Seed:
    org_a: Organization
    org_b: Organization
    owner: User
    foreign_owner: User
    application: Application
    job_version: JobVersion
    candidate: Candidate
    requirement_id: uuid.UUID
    document_id: uuid.UUID


class _Provider:
    """Proveedor determinista; solo responde al contrato de matching."""

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema, context
        self.calls += 1
        return _matching_output(self._seed)

    def _bind(self, seed: Seed) -> None:
        self._seed = seed

    def generate_text(self, prompt_version: str, context: Mapping[str, object]) -> str:
        del prompt_version, context
        return ""

    def health_check(self) -> bool:
        return True

    def estimate_usage(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> dict[str, int]:
        del prompt_version, context
        return {}


def _matching_output(seed: Seed) -> dict[str, object]:
    return {
        "evaluations": [
            {
                "requirement_id": str(seed.requirement_id),
                "status": RequirementEvaluationStatus.SUPPORTED.value,
                "evidence_refs": [
                    {
                        "document_id": str(seed.document_id),
                        "field_name": ExtractedFieldName.SKILLS.value,
                        "page": 1,
                        "quote": _QUOTE,
                        "offset": 0,
                    }
                ],
                "explanation": "Synthetic explanation",
                "limitations": [],
                "review_required": False,
            }
        ],
        "strengths": [],
        "gaps": [],
        "questions": [],
        "limitations": [],
        "review_required": False,
        "model_version": "test-model",
        "prompt_version": MATCHING_PROMPT_VERSION,
    }


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
def saver(engine: Engine) -> SQLAgentCheckpointSaver:
    return SQLAgentCheckpointSaver(lambda: DBSession(engine, expire_on_commit=False))


@pytest.fixture
def seed(db: DBSession) -> Seed:
    org_a = Organization(name="Orchestrator Org A", slug="orchestrator-org-a")
    org_b = Organization(name="Orchestrator Org B", slug="orchestrator-org-b")
    owner = User(
        email="owner-orchestrator@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Owner",
    )
    foreign_owner = User(
        email="foreign-orchestrator@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Foreign",
    )
    db.add_all([org_a, org_b, owner, foreign_owner])
    db.flush()
    db.add_all(
        [
            Membership(organization_id=org_a.id, user_id=owner.id, role=MembershipRole.OWNER),
            Membership(
                organization_id=org_b.id,
                user_id=foreign_owner.id,
                role=MembershipRole.OWNER,
            ),
        ]
    )
    job = Job(
        organization_id=org_a.id,
        owner_id=owner.id,
        title="Backend Engineer",
        description="Synthetic job",
        status=JobStatus.OPEN,
    )
    db.add(job)
    db.flush()
    requirement_id = uuid.uuid4()
    version = JobVersion(
        job_id=job.id,
        version=1,
        snapshot={
            "job": {"id": str(job.id), "organization_id": str(org_a.id)},
            "requirements": [
                {
                    "id": str(requirement_id),
                    "category": "skill",
                    "description": "Python",
                    "importance": "required",
                    "expected_level": "mid",
                }
            ],
        },
    )
    db.add(version)
    candidate = Candidate(
        organization_id=org_a.id,
        name="Synthetic Candidate",
        email="candidate-orchestrator@example.test",
    )
    db.add(candidate)
    db.flush()
    application = Application(
        organization_id=org_a.id,
        job_id=job.id,
        candidate_id=candidate.id,
        stage=ApplicationStage.APPLIED,
    )
    document = Document(
        organization_id=org_a.id,
        candidate_id=candidate.id,
        uploaded_by=owner.id,
        original_filename="synthetic.txt",
        internal_name="private/orchestrator-synthetic.txt",
        content_type="text/plain",
        extension="txt",
        size_bytes=len(_QUOTE.encode()),
        checksum_sha256="0" * 64,
        status=DocumentStatus.PROCESSED,
        page_count=1,
    )
    db.add_all([application, document])
    db.flush()
    extraction = DocumentExtraction(
        document_id=document.id,
        provider="mock",
        model="mock-v1",
        prompt_version="v1",
        status=ExtractionStatus.COMPLETED,
        pages=[{"page": 1, "text": f"{_QUOTE}\n{_CV_MARKER}\n{_SECRET_MARKER}"}],
    )
    db.add(extraction)
    db.flush()
    db.add(
        ExtractedField(
            extraction_id=extraction.id,
            field_name=ExtractedFieldName.SKILLS,
            value=["Python"],
            status=ExtractedFieldStatus.CONFIRMED,
            evidence=[
                {
                    "document_id": str(document.id),
                    "page": 1,
                    "quote": _QUOTE,
                    "offset": 0,
                }
            ],
            confirmed_by=owner.id,
            confirmed_at=datetime.now(UTC),
        )
    )
    db.commit()
    return Seed(
        org_a=org_a,
        org_b=org_b,
        owner=owner,
        foreign_owner=foreign_owner,
        application=application,
        job_version=version,
        candidate=candidate,
        requirement_id=requirement_id,
        document_id=document.id,
    )


@pytest.fixture
def provider(seed: Seed) -> _Provider:
    instance = _Provider()
    instance._bind(seed)
    return instance


@pytest.fixture
def client(engine: Engine, seed: Seed) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[DBSession]:
        with DBSession(engine, expire_on_commit=False) as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: seed.owner
    fastapi_app.dependency_overrides[get_current_organization] = lambda: seed.org_a
    fastapi_app.dependency_overrides[verify_origin] = lambda: None
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def _add_assessment(db: DBSession, seed: Seed) -> uuid.UUID:
    assessment = Assessment(
        organization_id=seed.org_a.id,
        application_id=seed.application.id,
        job_version_id=seed.job_version.id,
        candidate_id=seed.candidate.id,
        status=AssessmentStatus.COMPLETED,
        model_version="test-model",
        prompt_version="orchestrator-assessment-v1",
        summary={"strengths": [], "gaps": [], "questions": []},
        limitations=[],
        created_by=seed.owner.id,
    )
    db.add(assessment)
    db.commit()
    return assessment.id


def _add_guide(db: DBSession, seed: Seed) -> uuid.UUID:
    guide = InterviewGuide(
        organization_id=seed.org_a.id,
        application_id=seed.application.id,
        status=InterviewGuideStatus.DRAFT,
        version=1,
        title="Synthetic guide v1",
        created_by=seed.owner.id,
    )
    db.add(guide)
    db.commit()
    return guide.id


def _start(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
    *,
    key: str,
    organization_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    workflow: str = RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow,
) -> dict[str, object]:
    return service.start_workflow(
        db,
        organization_id=organization_id or seed.org_a.id,
        actor_id=actor_id or seed.owner.id,
        actor_role=MembershipRole.OWNER,
        application_id=seed.application.id,
        idempotency_key=key,
        workflow=workflow,
        provider=provider,
        checkpointer=saver,
    )


def _decide(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
    view: dict[str, object],
    decision: ApprovalStatus,
) -> dict[str, object]:
    return service.decide_approval(
        db,
        organization_id=seed.org_a.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        agent_run_id=uuid.UUID(str(view["agent_run_id"])),
        approval_id=uuid.UUID(str(view["approval_id"])),
        decision=decision,
        provider=provider,
        checkpointer=saver,
    )


def _resume(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
    view: dict[str, object],
) -> dict[str, object]:
    return service.resume_workflow(
        db,
        organization_id=seed.org_a.id,
        actor_id=seed.owner.id,
        actor_role=MembershipRole.OWNER,
        agent_run_id=uuid.UUID(str(view["agent_run_id"])),
        provider=provider,
        checkpointer=saver,
    )


def _child_runs(db: DBSession, seed: Seed) -> list[AgentRun]:
    return list(
        db.scalars(
            select(AgentRun).where(
                AgentRun.organization_id == seed.org_a.id,
                AgentRun.workflow == MATCHING_REVIEW_WORKFLOW.workflow,
            )
        ).all()
    )


def _checkpoint_text(db: DBSession, run_id: uuid.UUID) -> str:
    rows = db.scalars(
        select(AgentCheckpoint).where(AgentCheckpoint.agent_run_id == run_id)
    ).all()
    parts: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, Mapping):
            channel_values = value.get("channel_values")
            if isinstance(channel_values, Mapping):
                for encoded in channel_values.values():
                    if (
                        isinstance(encoded, (list, tuple))
                        and len(encoded) == 2
                        and encoded[0] == "json"
                        and isinstance(encoded[1], str)
                    ):
                        parts.append(base64.b64decode(encoded[1]).decode("utf-8"))
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            parts.append(value)

    for row in rows:
        walk(row.payload)
    return "\n".join(parts)


def _audit_count(db: DBSession, action: str) -> int:
    return int(
        db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        or 0
    )


def test_contract_is_explicit_ordered_and_read_only() -> None:
    contract = RECRUITMENT_ORCHESTRATION_WORKFLOW
    assert contract.workflow == "recruitment_orchestration"
    assert contract.version == "1.0.0"
    assert tuple(node.name.value for node in contract.nodes) == (
        "receive_task",
        "select_flow",
        "delegate",
        "request_approval",
        "finalize",
    )
    assert all(node.timeout_seconds == 2.0 for node in contract.nodes)
    assert all(node.max_retries == 1 for node in contract.nodes)
    assert contract.max_retries == 1
    assert contract.allowed_tools == frozenset(
        {
            "get_job_requirements",
            "get_candidate_profile",
            "get_confirmed_document_text",
        }
    )
    assert contract.approval_action_type == "delegate_specialized_flow"
    assert contract.interrupt_before_effects is OrchestrationNode.REQUEST_APPROVAL
    assert contract.terminal_statuses == MATCHING_REVIEW_WORKFLOW.terminal_statuses
    assert "create_assessment_draft" not in orchestrator.build_orchestration_registry().names()


def test_select_flow_uses_only_persisted_facts(db: DBSession, seed: Seed) -> None:
    select_flow = orchestrator.select_flow_from_persisted_facts
    assert select_flow(db, seed.org_a.id, seed.application.id) == "matching_review"
    assessment_id = _add_assessment(db, seed)
    assert assessment_id is not None
    assert select_flow(db, seed.org_a.id, seed.application.id) == "interview_guide"
    _add_guide(db, seed)
    assert select_flow(db, seed.org_a.id, seed.application.id) == "review_only"
    assert select_flow(db, seed.org_b.id, seed.application.id) == "matching_review"


def test_unknown_workflow_is_rejected_deterministically(
    db: DBSession, saver: SQLAgentCheckpointSaver, seed: Seed, provider: _Provider
) -> None:
    with pytest.raises(AgentDomainError, match="unknown_workflow"):
        _start(db, saver, seed, provider, key="unknown-workflow", workflow="not-a-contract")
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_interrupt_payload_is_sanitized_and_happens_before_delegation(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    def _capture(payload: object) -> object:
        captured.append(validate_safe_payload(cast(Mapping[str, object], payload)))
        return real_interrupt(payload)

    monkeypatch.setattr(orchestrator, "interrupt", _capture)
    view = _start(db, saver, seed, provider, key="interrupt-payload")

    assert view["status"] == "waiting_approval"
    assert view["next_nodes"] == [OrchestrationNode.REQUEST_APPROVAL.value]
    assert len(captured) == 1
    assert captured[0]["action_type"] == "delegate_specialized_flow"
    assert captured[0]["selected_flow"] == "matching_review"
    assert captured[0]["application_id"] == str(seed.application.id)
    assert _child_runs(db, seed) == []
    assert count_guides(db, seed.org_a.id, application_id=seed.application.id) == 0


def test_checkpoint_and_public_state_never_hold_cv_or_secrets(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    view = _start(db, saver, seed, provider, key="no-pii-state")
    state = cast(Mapping[str, object], view["state"])
    assert validate_safe_payload(state) == dict(state)
    assert state["selected_flow"] == "matching_review"
    assert state["delegated_run_id"] is None
    assert state["delegated_guide_id"] is None

    text = _checkpoint_text(db, uuid.UUID(str(view["agent_run_id"])))
    assert "selected_flow" in text
    for marker in (_CV_MARKER, _SECRET_MARKER, "chain_of_thought"):
        assert marker not in text


def test_resume_requires_resolved_contract_approval_before_any_effect(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    view = _start(db, saver, seed, provider, key="approval-gate")
    run_id = uuid.UUID(str(view["agent_run_id"]))

    with pytest.raises(AgentDomainError, match="approval_pending"):
        _resume(db, saver, seed, provider, view)

    wrong = create_approval(
        db,
        organization_id=seed.org_a.id,
        agent_run_id=run_id,
        action_type=MATCHING_REVIEW_WORKFLOW.approval_action_type,
        payload={"action_type": "create_assessment", "application_id": str(seed.application.id)},
    )
    _decide(
        db,
        saver,
        seed,
        provider,
        {**view, "approval_id": str(wrong.id)},
        ApprovalStatus.APPROVED,
    )
    with pytest.raises(AgentDomainError, match="approval_pending"):
        _resume(db, saver, seed, provider, view)
    assert _child_runs(db, seed) == []

    _decide(db, saver, seed, provider, view, ApprovalStatus.APPROVED)
    finished = _resume(db, saver, seed, provider, view)
    assert finished["status"] == "completed"


def test_rejection_cancels_without_delegation(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    view = _start(db, saver, seed, provider, key="rejected-flow")
    _decide(db, saver, seed, provider, view, ApprovalStatus.REJECTED)
    finished = _resume(db, saver, seed, provider, view)

    assert finished["status"] == "cancelled"
    assert _child_runs(db, seed) == []
    assert count_guides(db, seed.org_a.id, application_id=seed.application.id) == 0
    assert cast(Mapping[str, object], finished["state"])["delegated_run_id"] is None


def test_approval_delegates_to_existing_matching_workflow(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    view = _start(db, saver, seed, provider, key="delegate-matching")
    run_id = uuid.UUID(str(view["agent_run_id"]))
    _decide(db, saver, seed, provider, view, ApprovalStatus.APPROVED)
    finished = _resume(db, saver, seed, provider, view)

    children = _child_runs(db, seed)
    assert finished["status"] == "completed"
    assert len(children) == 1
    assert children[0].idempotency_key == f"orchestration-child:{run_id}"
    assert children[0].status is AgentRunStatus.WAITING_APPROVAL
    parent = db.get(AgentRun, run_id)
    assert parent is not None
    assert parent.output_ref == f"child:{children[0].id}"
    assert cast(Mapping[str, object], finished["state"])["delegated_run_id"] == str(children[0].id)
    assert count_guides(db, seed.org_a.id, application_id=seed.application.id) == 0


def test_approval_delegates_to_interview_guide_service(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    _add_assessment(db, seed)
    view = _start(db, saver, seed, provider, key="delegate-guide")
    assert cast(Mapping[str, object], view["state"])["selected_flow"] == "interview_guide"
    _decide(db, saver, seed, provider, view, ApprovalStatus.APPROVED)
    finished = _resume(db, saver, seed, provider, view)

    guide_id = cast(Mapping[str, object], finished["state"])["delegated_guide_id"]
    parent = db.get(AgentRun, uuid.UUID(str(finished["agent_run_id"])))
    assert parent is not None
    assert finished["status"] == "completed"
    assert parent.output_ref == f"guide:{guide_id}"
    assert count_guides(db, seed.org_a.id, application_id=seed.application.id) == 1
    assert _child_runs(db, seed) == []


def test_review_only_creates_nothing(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    _add_assessment(db, seed)
    guide_id = _add_guide(db, seed)
    view = _start(db, saver, seed, provider, key="review-only")
    assert cast(Mapping[str, object], view["state"])["selected_flow"] == "review_only"
    _decide(db, saver, seed, provider, view, ApprovalStatus.APPROVED)
    finished = _resume(db, saver, seed, provider, view)

    state = cast(Mapping[str, object], finished["state"])
    assert finished["status"] == "completed"
    assert state["delegated_run_id"] is None
    assert state["delegated_guide_id"] is None
    assert _child_runs(db, seed) == []
    assert count_guides(db, seed.org_a.id, application_id=seed.application.id) == 1
    assert db.get(InterviewGuide, guide_id) is not None


def test_foreign_tenant_cannot_start_orchestration(
    db: DBSession,
    saver: SQLAgentCheckpointSaver,
    seed: Seed,
    provider: _Provider,
) -> None:
    with pytest.raises(AgentDomainError, match="no disponible"):
        _start(
            db,
            saver,
            seed,
            provider,
            key="foreign-tenant",
            organization_id=seed.org_b.id,
            actor_id=seed.foreign_owner.id,
        )
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_http_endpoint_keeps_existing_run_contracts_and_audit(
    client: TestClient,
    db: DBSession,
    engine: Engine,
    seed: Seed,
    provider: _Provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    monkeypatch.setattr(
        service,
        "SessionLocal",
        lambda: DBSession(engine, expire_on_commit=False),
    )
    correlation = str(uuid.uuid4())
    body = {
        "application_id": str(seed.application.id),
        "idempotency_key": "api-orchestration",
        "correlation_id": correlation,
    }
    first = client.post(f"{_URL}/orchestration/runs", json=body)
    assert first.status_code == 201, first.text
    created = first.json()
    assert created["workflow"] == RECRUITMENT_ORCHESTRATION_WORKFLOW.workflow
    assert created["version"] == RECRUITMENT_ORCHESTRATION_WORKFLOW.version
    assert created["status"] == "waiting_approval"
    assert created["correlation_id"] == correlation

    repeated = client.post(f"{_URL}/orchestration/runs", json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == created["id"]
    assert _audit_count(db, "agent.run_started") == 1

    run_id = str(created["id"])
    detail_text = json.dumps(client.get(f"{_URL}/runs/{run_id}").json(), ensure_ascii=False)
    events = client.get(f"{_URL}/runs/{run_id}/events")
    approvals = client.get(f"{_URL}/runs/{run_id}/approvals")
    assert detail_text.find(_CV_MARKER) == -1
    for marker in (_CV_MARKER, _SECRET_MARKER, str(seed.org_a.id)):
        assert marker not in json.dumps(events.json(), ensure_ascii=False)
        assert marker not in json.dumps(approvals.json(), ensure_ascii=False)
    assert events.json()["total"] >= 1
    assert approvals.json()[0]["action_type"] == "delegate_specialized_flow"
    assert approvals.json()[0]["status"] == "pending"

    approval_id = str(approvals.json()[0]["id"])
    decision = client.post(
        f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
        json={"decision": "approved"},
    )
    assert decision.status_code == 200, decision.text
    assert _audit_count(db, "agent.approval_decided") == 1

    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        agents_tasks.resume_agent_workflow,
        "delay",
        lambda *args: calls.append(args),
    )
    resumed = client.post(f"{_URL}/runs/{run_id}/resume")
    assert resumed.status_code == 202, resumed.text
    assert resumed.json()["queued"] is True
    assert len(calls) == 1

    cancelled = client.post(f"{_URL}/runs/{run_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert _audit_count(db, "agent.run_cancelled") == 1
