from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import email_validator
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents import service as agents_service
from app.agents import tasks as agents_tasks
from app.agents.contracts import MATCHING_REVIEW_WORKFLOW
from app.agents.matching_analyst import PROMPT_VERSION
from app.agents.models import AgentRun, Approval, ApprovalStatus
from app.api.routes import agents as agents_routes
from app.applications.models import Application, ApplicationStage
from app.assessment.models import RequirementEvaluationStatus
from app.audit.models import AuditLog
from app.candidates.models import Candidate
from app.core.config import get_settings
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
from app.identity.models import User
from app.jobs.models import Job, JobStatus, JobVersion
from app.main import app

_URL = "/api/v1/agents"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-agents-api@example.test"
_OWNER_B = "owner-b-agents-api@example.test"
_RECRUITER = "recruiter-agents-api@example.test"
_REVIEWER = "reviewer-agents-api@example.test"

_QUOTE = "Skills: Python"
_CV_MARKER = "SyntheticCvMarkerDoNotExpose"
_STORAGE_MARKER = "private/synthetic-cv-path.txt"
_SECRET_MARKER = "SyntheticSecretMarkerDoNotExpose"


@dataclass(frozen=True)
class _Seed:
    org_a: str
    org_b: str
    owner_a_id: str
    owner_b_id: str
    application_id: str
    requirement_id: uuid.UUID
    document_id: uuid.UUID


class _Provider:
    """Proveedor determinista sin red; devuelve un dict validado por el workflow."""

    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls = 0

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema, context
        self.calls += 1
        return self.output

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


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


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
def client(engine: Engine) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[DBSession]:
        with DBSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "name": name},
    )
    assert response.status_code == 201, response.text


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert _COOKIE in client.cookies


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORGS_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
def seeded(client: TestClient, db: DBSession) -> _Seed:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Owner B"),
        (_RECRUITER, "Synthetic Recruiter"),
        (_REVIEWER, "Synthetic Reviewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Agents Org A", "agents-org-a")
    for email, role in ((_RECRUITER, "recruiter"), (_REVIEWER, "reviewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers={"X-Organization-ID": org_a},
        )
        assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Agents Org B", "agents-org-b")
    user_ids = {
        row.email: str(row.id)
        for row in db.scalars(select(User)).all()
        if row.email in {_OWNER_A, _OWNER_B}
    }

    org_a_uuid = uuid.UUID(org_a)
    owner_a_uuid = uuid.UUID(user_ids[_OWNER_A])
    candidate = Candidate(
        organization_id=org_a_uuid,
        name="Synthetic Candidate",
        email="candidate-agents-api@example.test",
    )
    db.add(candidate)
    db.flush()
    job = Job(
        organization_id=org_a_uuid,
        owner_id=owner_a_uuid,
        title="Synthetic role",
        description="Synthetic job",
        status=JobStatus.OPEN,
    )
    db.add(job)
    db.flush()
    requirement_id = uuid.uuid4()
    db.add(
        JobVersion(
            job_id=job.id,
            version=1,
            snapshot={
                "job": {"id": str(job.id), "organization_id": str(org_a_uuid)},
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
    )
    application = Application(
        organization_id=org_a_uuid,
        job_id=job.id,
        candidate_id=candidate.id,
        stage=ApplicationStage.APPLIED,
    )
    document = Document(
        organization_id=org_a_uuid,
        candidate_id=candidate.id,
        uploaded_by=owner_a_uuid,
        original_filename="synthetic.txt",
        internal_name=_STORAGE_MARKER,
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
        pages=[{"page": 1, "text": f"{_QUOTE}\n{_CV_MARKER}"}],
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
            confirmed_by=owner_a_uuid,
            confirmed_at=datetime.now(UTC),
        )
    )
    db.commit()
    _login(client, _OWNER_A)
    return _Seed(
        org_a=org_a,
        org_b=org_b,
        owner_a_id=user_ids[_OWNER_A],
        owner_b_id=user_ids[_OWNER_B],
        application_id=str(application.id),
        requirement_id=requirement_id,
        document_id=document.id,
    )


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, engine: Engine, seeded: _Seed) -> _Provider:
    """Fija proveedor y checkpointer sobre SQLite en memoria, sin red ni Postgres."""
    provider = _Provider(_output(seeded))
    monkeypatch.setattr(agents_service, "get_llm_provider", lambda: provider)
    monkeypatch.setattr(
        agents_service,
        "SessionLocal",
        lambda: DBSession(engine, expire_on_commit=False),
    )
    return provider


def _output(seed: _Seed) -> dict[str, object]:
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
                "explanation": _SECRET_MARKER,
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
        "prompt_version": PROMPT_VERSION,
    }


def _headers(seeded: _Seed, tenant: str = "a") -> dict[str, str]:
    return {
        "X-Organization-ID": seeded.org_a if tenant == "a" else seeded.org_b
    }


def _start_run(
    client: TestClient,
    seeded: _Seed,
    *,
    key: str,
    correlation: str | None = None,
    expected: int = 201,
    tenant: str = "a",
) -> dict[str, object]:
    body: dict[str, object] = {
        "application_id": seeded.application_id,
        "idempotency_key": key,
    }
    if correlation:
        body["correlation_id"] = correlation
    response = client.post(
        f"{_URL}/runs", json=body, headers=_headers(seeded, tenant)
    )
    assert response.status_code == expected, response.text
    return response.json()


def _approval_id(
    client: TestClient, seeded: _Seed, run_id: str, tenant: str = "a"
) -> str:
    response = client.get(
        f"{_URL}/runs/{run_id}/approvals", headers=_headers(seeded, tenant)
    )
    assert response.status_code == 200, response.text
    approvals = response.json()
    assert len(approvals) == 1
    return str(approvals[0]["id"])


def _audit_count(db: DBSession, action: str) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
        or 0
    )


def test_start_run_creates_once_and_reuses_idempotency_key(
    client: TestClient, db: DBSession, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    correlation = str(uuid.uuid4())
    first = _start_run(client, seeded, key="start-once", correlation=correlation)
    assert first["status"] == "waiting_approval"
    assert first["correlation_id"] == correlation
    assert first["workflow"] == MATCHING_REVIEW_WORKFLOW.workflow

    repeated = _start_run(
        client,
        seeded,
        key="start-once",
        correlation=str(uuid.uuid4()),
        expected=200,
    )
    assert repeated["id"] == first["id"]
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert _audit_count(db, "agent.run_started") == 1
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "agent.run_started"))
    assert audit is not None
    assert audit.actor_id == uuid.UUID(seeded.owner_a_id)
    assert audit.organization_id == uuid.UUID(seeded.org_a)


def test_detail_events_and_approvals_expose_no_sensitive_data(
    client: TestClient, db: DBSession, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    run = _start_run(client, seeded, key="no-pii")
    run_id = str(run["id"])
    detail = client.get(f"{_URL}/runs/{run_id}", headers=_headers(seeded))
    assert detail.status_code == 200
    detail_text = json.dumps(detail.json(), ensure_ascii=False)
    for marker in (_CV_MARKER, _STORAGE_MARKER, _SECRET_MARKER, seeded.org_a):
        assert marker not in detail_text
    assert detail.json()["event_count"] >= 1
    assert isinstance(detail.json()["duration_ms"], int)
    assert detail.json()["duration_ms"] >= 0
    settings = get_settings()
    assert detail.json()["configured_provider"] == settings.LLM_PROVIDER
    assert detail.json()["configured_model"] == (settings.LLM_MODEL.strip() or None)
    application = db.get(Application, uuid.UUID(seeded.application_id))
    assert application is not None
    assert detail.json()["job_id"] == str(application.job_id)
    assert detail.json()["candidate_id"] == str(application.candidate_id)

    events = client.get(f"{_URL}/runs/{run_id}/events", headers=_headers(seeded))
    assert events.status_code == 200
    event_text = json.dumps(events.json(), ensure_ascii=False)
    for marker in (_CV_MARKER, _STORAGE_MARKER, _SECRET_MARKER, seeded.org_a):
        assert marker not in event_text
    assert events.json()["total"] >= 1
    assert all("organization_id" not in item["payload"] for item in events.json()["items"])

    approvals = client.get(f"{_URL}/runs/{run_id}/approvals", headers=_headers(seeded))
    assert approvals.status_code == 200
    approval_text = json.dumps(approvals.json(), ensure_ascii=False)
    assert "payload" not in approval_text
    assert seeded.org_a not in approval_text
    assert approvals.json()[0]["action_type"] == "create_assessment"
    assert approvals.json()[0]["status"] == "pending"


def test_decision_records_actor_date_and_audit(
    client: TestClient, db: DBSession, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    run = _start_run(client, seeded, key="decide-actor")
    run_id = str(run["id"])
    approval_id = _approval_id(client, seeded, run_id)

    response = client.post(
        f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
        json={"decision": "approved", "note": "Synthetic note"},
        headers=_headers(seeded),
    )
    assert response.status_code == 200, response.text

    approval = db.get(Approval, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.status is ApprovalStatus.APPROVED
    assert approval.decided_by == uuid.UUID(seeded.owner_a_id)
    assert approval.decided_at is not None
    assert _audit_count(db, "agent.approval_decided") == 1
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "agent.approval_decided"))
    assert audit is not None
    assert audit.actor_id == uuid.UUID(seeded.owner_a_id)
    assert audit.resource_id == uuid.UUID(approval_id)


def test_reviewer_cannot_write(
    client: TestClient, db: DBSession, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    run = _start_run(client, seeded, key="reviewer-denied")
    run_id = str(run["id"])
    approval_id = _approval_id(client, seeded, run_id)
    _login(client, _REVIEWER)

    assert (
        client.post(
            f"{_URL}/runs",
            json={
                "application_id": seeded.application_id,
                "idempotency_key": "reviewer-run",
            },
            headers=_headers(seeded),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
            json={"decision": "approved"},
            headers=_headers(seeded),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{_URL}/runs/{run_id}/resume", headers=_headers(seeded)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{_URL}/runs/{run_id}/cancel", headers=_headers(seeded)
        ).status_code
        == 403
    )
    assert _audit_count(db, "agent.run_cancelled") == 0
    assert _audit_count(db, "agent.approval_decided") == 0


def test_resume_enqueues_context_and_rejects_other_tenant(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    runtime: _Provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del runtime
    run = _start_run(client, seeded, key="resume-context")
    run_id = str(run["id"])
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        agents_routes.resume_agent_workflow,
        "delay",
        lambda *args: calls.append(args),
    )

    _login(client, _OWNER_B)
    foreign = client.post(
        f"{_URL}/runs/{run_id}/resume", headers=_headers(seeded, "b")
    )
    assert foreign.status_code == 404
    assert calls == []

    _login(client, _OWNER_A)
    response = client.post(
        f"{_URL}/runs/{run_id}/resume", headers=_headers(seeded)
    )
    assert response.status_code == 202, response.text
    assert response.json()["queued"] is True
    assert response.json()["status"] == "waiting_approval"
    assert calls == [
        (
            seeded.org_a,
            seeded.owner_a_id,
            "owner",
            run_id,
            run["correlation_id"],
        )
    ]
    detail = client.get(f"{_URL}/runs/{run_id}", headers=_headers(seeded))
    assert detail.json()["status"] == "waiting_approval"
    assert db.get(AgentRun, uuid.UUID(run_id)) is not None


def test_broker_failure_returns_503_without_state_change(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    runtime: _Provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del runtime
    run = _start_run(client, seeded, key="broker-down")
    run_id = str(run["id"])

    def _raise_broker(*args: object) -> None:
        del args
        raise RuntimeError("broker connection refused at redis://internal")

    monkeypatch.setattr(agents_routes.resume_agent_workflow, "delay", _raise_broker)
    response = client.post(
        f"{_URL}/runs/{run_id}/resume", headers=_headers(seeded)
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "broker_unavailable"
    assert "connection refused" not in response.text
    assert "redis://" not in response.text

    detail = client.get(f"{_URL}/runs/{run_id}", headers=_headers(seeded))
    assert detail.json()["status"] == "waiting_approval"
    approvals = client.get(f"{_URL}/runs/{run_id}/approvals", headers=_headers(seeded))
    assert approvals.json()[0]["status"] == "pending"
    assert approvals.json()[0]["decided_at"] is None
    assert _audit_count(db, "agent.run_cancelled") == 0


def test_cancel_reaches_terminal_state_and_audits_once(
    client: TestClient, db: DBSession, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    run = _start_run(client, seeded, key="cancel-once")
    run_id = str(run["id"])

    response = client.post(
        f"{_URL}/runs/{run_id}/cancel", headers=_headers(seeded)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] in MATCHING_REVIEW_WORKFLOW.terminal_statuses
    assert response.json()["status"] == "cancelled"
    assert _audit_count(db, "agent.run_cancelled") == 1

    repeated = client.post(
        f"{_URL}/runs/{run_id}/cancel", headers=_headers(seeded)
    )
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"
    assert _audit_count(db, "agent.run_cancelled") == 1


def test_auth_and_tenant_boundaries(
    client: TestClient, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    run = _start_run(client, seeded, key="tenant-boundary")
    run_id = str(run["id"])
    approval_id = _approval_id(client, seeded, run_id)

    client.cookies.clear()
    anonymous = client.post(
        f"{_URL}/runs",
        json={
            "application_id": seeded.application_id,
            "idempotency_key": "anonymous-run",
        },
        headers=_headers(seeded),
    )
    assert anonymous.status_code == 401

    _login(client, _OWNER_B)
    wrong_org = client.get(f"{_URL}/runs", headers=_headers(seeded))
    assert wrong_org.status_code == 403

    foreign_headers = _headers(seeded, "b")
    for path in (
        f"{_URL}/runs/{run_id}",
        f"{_URL}/runs/{run_id}/events",
        f"{_URL}/runs/{run_id}/approvals",
    ):
        assert client.get(path, headers=foreign_headers).status_code == 404
    assert (
        client.post(
            f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
            json={"decision": "approved"},
            headers=foreign_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{_URL}/runs/{run_id}/cancel", headers=foreign_headers
        ).status_code
        == 404
    )


def test_list_is_paginated_filtered_and_tenant_scoped(
    client: TestClient, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    for index in range(3):
        _start_run(client, seeded, key=f"list-{index}")
    cancelled_id = str(
        client.get(f"{_URL}/runs?limit=10", headers=_headers(seeded)).json()["items"][0]["id"]
    )
    client.post(f"{_URL}/runs/{cancelled_id}/cancel", headers=_headers(seeded))

    first_page = client.get(
        f"{_URL}/runs?limit=2&offset=0", headers=_headers(seeded)
    )
    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["limit"] == 2
    assert first_page.json()["offset"] == 0

    second_page = client.get(
        f"{_URL}/runs?limit=2&offset=2", headers=_headers(seeded)
    )
    assert len(second_page.json()["items"]) == 1

    cancelled = client.get(
        f"{_URL}/runs?status=cancelled", headers=_headers(seeded)
    )
    assert cancelled.json()["total"] == 1
    by_workflow = client.get(
        f"{_URL}/runs?workflow={MATCHING_REVIEW_WORKFLOW.workflow}",
        headers=_headers(seeded),
    )
    assert by_workflow.json()["total"] == 3

    _login(client, _OWNER_B)
    other_tenant = client.get(f"{_URL}/runs", headers=_headers(seeded, "b"))
    assert other_tenant.json()["total"] == 0


def test_invalid_decision_returns_400(
    client: TestClient, seeded: _Seed, runtime: _Provider
) -> None:
    del runtime
    run = _start_run(client, seeded, key="invalid-decision")
    run_id = str(run["id"])
    approval_id = _approval_id(client, seeded, run_id)

    response = client.post(
        f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
        json={"decision": "maybe"},
        headers=_headers(seeded),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
    approvals = client.get(f"{_URL}/runs/{run_id}/approvals", headers=_headers(seeded))
    assert approvals.json()[0]["status"] == "pending"


def test_worker_rejects_foreign_tenant_before_resume(
    client: TestClient,
    engine: Engine,
    seeded: _Seed,
    runtime: _Provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del runtime
    run = _start_run(client, seeded, key="worker-tenant")
    run_id = str(run["id"])

    def _forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("worker reached resume_workflow for a foreign tenant")

    monkeypatch.setattr(
        agents_tasks,
        "SessionLocal",
        lambda: DBSession(engine, expire_on_commit=False),
    )
    monkeypatch.setattr(agents_service, "resume_workflow", _forbidden)
    agents_tasks.resume_agent_workflow(
        seeded.org_b,
        seeded.owner_b_id,
        "owner",
        run_id,
        str(run["correlation_id"]),
    )
    detail = client.get(f"{_URL}/runs/{run_id}", headers=_headers(seeded))
    assert detail.json()["status"] == "waiting_approval"

