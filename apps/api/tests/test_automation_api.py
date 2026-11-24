"""Tests de integración de la API REST y el worker de automatizaciones.

SQLite aislada, cookies y headers reales, cola mockeada y datos sintéticos.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import email_validator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.automation.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.api.routes import automation as automation_routes
from app.applications.models import Application, ApplicationStage, StageChange
from app.audit.models import AuditLog
from app.automation import tasks as automation_tasks
from app.automation.models import (
    AutomationApproval,
    AutomationApprovalStatus,
    AutomationRun,
    AutomationRunEventType,
)
from app.automation.repositories import list_run_events
from app.candidates.models import Candidate
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.documents.models import Document, DocumentStatus
from app.identity.models import User
from app.jobs.models import Job, JobStatus
from app.main import app

_URL = "/api/v1/automations"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-automation-api@example.test"
_OWNER_B = "owner-b-automation-api@example.test"
_RECRUITER = "recruiter-automation-api@example.test"
_REVIEWER = "reviewer-automation-api@example.test"
_CANDIDATE_EMAIL = "candidate-automation-api@example.test"
_CV_MARKER = "SyntheticCvMarkerDoNotExpose"
_SECRET_MARKER = "SyntheticSecretMarkerDoNotExpose"
_STORAGE_MARKER = "private/synthetic-cv-path.txt"


@dataclass(frozen=True)
class _Seed:
    org_a: str
    org_b: str
    owner_a_id: str
    owner_b_id: str
    application_id: str
    document_id: uuid.UUID


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
    def _foreign_keys(dbapi_connection: object, _record: object) -> None:
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


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    """Captura el contexto encolado sin broker ni tareas reales."""
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        automation_routes.automation_tasks.execute_run,
        "delay",
        lambda *args: calls.append(args),
    )
    return calls


@pytest.fixture
def task_sessions(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """El worker abre su propia sesión, contra la SQLite aislada del test."""
    monkeypatch.setattr(
        automation_tasks,
        "SessionLocal",
        lambda: DBSession(engine, expire_on_commit=False),
    )


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


def _headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


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
    org_a = _create_org(client, "Automation Org A", "automation-org-a")
    for email, role in ((_RECRUITER, "recruiter"), (_REVIEWER, "reviewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers=_headers(org_a),
        )
        assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Automation Org B", "automation-org-b")

    user_ids = {
        row.email: str(row.id)
        for row in db.scalars(select(User)).all()
        if row.email in {_OWNER_A, _OWNER_B}
    }
    candidate = Candidate(
        organization_id=uuid.UUID(org_a),
        name=f"Synthetic Candidate {_CV_MARKER}",
        email=_CANDIDATE_EMAIL,
    )
    db.add(candidate)
    db.flush()
    job = Job(
        organization_id=uuid.UUID(org_a),
        owner_id=uuid.UUID(user_ids[_OWNER_A]),
        title="Synthetic role",
        description="Synthetic description",
        status=JobStatus.OPEN,
    )
    db.add(job)
    db.flush()
    application = Application(
        organization_id=uuid.UUID(org_a),
        job_id=job.id,
        candidate_id=candidate.id,
        stage=ApplicationStage.INTERVIEW,
    )
    db.add(application)
    db.flush()
    document = Document(
        organization_id=uuid.UUID(org_a),
        candidate_id=candidate.id,
        uploaded_by=uuid.UUID(user_ids[_OWNER_A]),
        original_filename="synthetic.txt",
        internal_name=_STORAGE_MARKER,
        content_type="text/plain",
        extension="txt",
        size_bytes=1,
        checksum_sha256="0" * 64,
        status=DocumentStatus.PROCESSED,
        page_count=1,
    )
    db.add(document)
    db.flush()
    db.add(
        StageChange(
            application_id=application.id,
            from_stage=ApplicationStage.SCREENING,
            to_stage=ApplicationStage.INTERVIEW,
            actor_id=uuid.UUID(user_ids[_OWNER_A]),
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
        document_id=document.id,
    )


def _create_rule(
    client: TestClient, seed: _Seed, *, name: str = "Synthetic rule"
) -> str:
    response = client.post(
        _URL, json={"name": name}, headers=_headers(seed.org_a)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _add_version(
    client: TestClient,
    seed: _Seed,
    rule_id: str,
    *,
    actions: list[dict[str, object]] | None = None,
) -> None:
    body: dict[str, object] = {
        "trigger": {"event_type": "application.stage_changed"},
        "conditions": [{"field": "to_stage", "operator": "eq", "value": "interview"}],
        "actions": actions
        or [
            {
                "type": "create_message_draft",
                "payload": {"template_id": "synthetic-template"},
            }
        ],
    }
    response = client.post(
        f"{_URL}/{rule_id}/versions", json=body, headers=_headers(seed.org_a)
    )
    assert response.status_code == 201, response.text
    assert response.json()["version"] == 1


def _activate(client: TestClient, seed: _Seed, rule_id: str) -> None:
    response = client.patch(
        f"{_URL}/{rule_id}", json={"status": "active"}, headers=_headers(seed.org_a)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"


def _ready_rule(
    client: TestClient,
    seed: _Seed,
    *,
    actions: list[dict[str, object]] | None = None,
) -> str:
    rule_id = _create_rule(client, seed)
    _add_version(client, seed, rule_id, actions=actions)
    _activate(client, seed, rule_id)
    return rule_id


def _post_execution(
    client: TestClient,
    seed: _Seed,
    rule_id: str,
    endpoint: str,
    *,
    key: str,
    correlation: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "application_id": seed.application_id,
        "idempotency_key": key,
    }
    if correlation is not None:
        body["correlation_id"] = correlation
    response = client.post(
        f"{_URL}/{rule_id}/{endpoint}", json=body, headers=_headers(seed.org_a)
    )
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()


def _approval_id(client: TestClient, seed: _Seed, run_id: str) -> str:
    response = client.get(
        f"{_URL}/runs/{run_id}/approvals", headers=_headers(seed.org_a)
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


def _execute_worker(
    seed: _Seed,
    run_id: str,
    correlation: str,
    *,
    org_id: str | None = None,
    actor_id: str | None = None,
    role: str = "owner",
) -> None:
    automation_tasks.execute_run(
        org_id or seed.org_a,
        actor_id or seed.owner_a_id,
        role,
        run_id,
        correlation,
    )


def test_create_rule_and_immutable_version_are_audited(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    created = client.post(
        _URL, json={"name": "Synthetic rule"}, headers=_headers(seeded.org_a)
    )
    assert created.status_code == 201, created.text
    rule_id = str(created.json()["id"])
    assert created.json()["status"] == "draft"
    assert created.json()["current_version"] == 1
    assert "organization_id" not in created.text

    body = {
        "trigger": {"event_type": "application.stage_changed"},
        "conditions": [{"field": "to_stage", "operator": "eq", "value": "interview"}],
        "actions": [{"type": "record_note"}],
    }
    version = client.post(
        f"{_URL}/{rule_id}/versions", json=body, headers=_headers(seeded.org_a)
    )
    assert version.status_code == 201, version.text
    assert version.json()["version"] == 1

    detail = client.get(f"{_URL}/{rule_id}", headers=_headers(seeded.org_a))
    assert detail.status_code == 200, detail.text
    assert detail.json()["current_version"] == 1
    assert detail.json()["active_version"]["actions"][0]["type"] == "record_note"
    assert _audit_count(db, "automation.created") == 1
    assert _audit_count(db, "automation.version_created") == 1


def test_list_and_detail_are_paginated_and_sanitized(
    client: TestClient, seeded: _Seed
) -> None:
    first = _create_rule(client, seeded, name="Synthetic rule A")
    _add_version(client, seeded, first)
    _create_rule(client, seeded, name="Synthetic rule B")

    listing = client.get(
        f"{_URL}?status=draft&limit=1&offset=0", headers=_headers(seeded.org_a)
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 2
    assert len(listing.json()["items"]) == 1
    assert listing.json()["limit"] == 1

    detail = client.get(f"{_URL}/{first}", headers=_headers(seeded.org_a))
    assert detail.status_code == 200, detail.text
    for marker in (
        _CANDIDATE_EMAIL,
        _CV_MARKER,
        _STORAGE_MARKER,
        _SECRET_MARKER,
        "organization_id",
        "internal_name",
    ):
        assert marker not in detail.text

    test_run = _post_execution(
        client, seeded, first, "test", key="listing-dry-run"
    )
    events = client.get(
        f"{_URL}/runs/{test_run['id']}/events", headers=_headers(seeded.org_a)
    )
    assert events.status_code == 200, events.text
    for marker in (_CANDIDATE_EMAIL, _CV_MARKER, _STORAGE_MARKER, _SECRET_MARKER):
        assert marker not in events.text


def test_test_mode_is_idempotent_and_has_no_effects(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    rule_id = _ready_rule(client, seeded)
    correlation = str(uuid.uuid4())
    first = _post_execution(
        client, seeded, rule_id, "test", key="dry-run-once", correlation=correlation
    )
    second = _post_execution(
        client, seeded, rule_id, "test", key="dry-run-once", correlation=correlation
    )
    assert first["id"] == second["id"]
    assert first["status"] == "completed"
    assert first["mode"] == "test"
    assert first["correlation_id"] == correlation
    types = {item["event_type"] for item in first["event_summary"]}
    assert "dry_run" in types
    assert "action_planned" in types

    approvals = client.get(
        f"{_URL}/runs/{first['id']}/approvals", headers=_headers(seeded.org_a)
    )
    assert approvals.json() == []
    assert _audit_count(db, "automation.test_executed") == 1
    application = db.get(Application, uuid.UUID(seeded.application_id))
    assert application is not None
    assert application.stage is ApplicationStage.INTERVIEW


def test_run_enqueues_minimal_context(
    client: TestClient, db: DBSession, seeded: _Seed, queued: list[tuple[object, ...]]
) -> None:
    rule_id = _ready_rule(client, seeded)
    correlation = str(uuid.uuid4())
    run = _post_execution(
        client, seeded, rule_id, "run", key="run-context", correlation=correlation
    )
    assert run["queued"] is True
    assert run["status"] == "pending"
    assert run["correlation_id"] == correlation
    assert queued == [
        (seeded.org_a, seeded.owner_a_id, "owner", run["id"], correlation)
    ]

    detail = client.get(
        f"{_URL}/runs/{run['id']}", headers=_headers(seeded.org_a)
    )
    assert detail.json()["status"] == "pending"
    assert "application_id" not in detail.text
    assert "organization_id" not in detail.text
    assert _audit_count(db, "automation.run_started") == 1


def test_broker_failure_returns_503_without_run_or_state_change(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_id = _ready_rule(client, seeded)

    def _raise_broker(*args: object) -> None:
        del args
        raise RuntimeError("broker refused at redis://internal-secret")

    monkeypatch.setattr(
        automation_routes.automation_tasks.execute_run, "delay", _raise_broker
    )
    response = client.post(
        f"{_URL}/{rule_id}/run",
        json={
            "application_id": seeded.application_id,
            "idempotency_key": "broker-down",
        },
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "broker_unavailable"
    assert "redis://" not in response.text
    assert "internal-secret" not in response.text

    stored = db.scalar(
        select(func.count())
        .select_from(AutomationRun)
        .where(AutomationRun.idempotency_key == "broker-down")
    )
    assert stored == 0
    assert _audit_count(db, "automation.run_started") == 0


def test_worker_validates_tenant_and_correlation_then_executes(
    client: TestClient,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    del task_sessions
    rule_id = _ready_rule(client, seeded)
    correlation = str(uuid.uuid4())
    run = _post_execution(
        client, seeded, rule_id, "run", key="worker-exec", correlation=correlation
    )
    run_id = str(run["id"])

    original = automation_tasks.automation_service.execute_pending_run

    def _forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("worker reached the domain for an invalid context")

    monkeypatch.setattr(
        automation_tasks.automation_service, "execute_pending_run", _forbidden
    )
    _execute_worker(seeded, run_id, correlation, org_id=seeded.org_b)
    _execute_worker(seeded, run_id, str(uuid.uuid4()))
    detail = client.get(f"{_URL}/runs/{run_id}", headers=_headers(seeded.org_a))
    assert detail.json()["status"] == "pending"

    monkeypatch.setattr(
        automation_tasks.automation_service, "execute_pending_run", original
    )
    with caplog.at_level(logging.INFO):
        _execute_worker(seeded, run_id, correlation)
    assert "organization_mismatch" in caplog.text
    assert "correlation_mismatch" in caplog.text
    for marker in (_CANDIDATE_EMAIL, _CV_MARKER, _STORAGE_MARKER, _SECRET_MARKER):
        assert marker not in caplog.text

    detail = client.get(f"{_URL}/runs/{run_id}", headers=_headers(seeded.org_a))
    assert detail.json()["status"] == "waiting_approval"
    assert _approval_id(client, seeded, run_id)


def test_decision_records_session_actor_and_date(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
) -> None:
    del queued, task_sessions
    rule_id = _ready_rule(client, seeded)
    correlation = str(uuid.uuid4())
    run = _post_execution(
        client, seeded, rule_id, "run", key="decide-approve", correlation=correlation
    )
    run_id = str(run["id"])
    _execute_worker(seeded, run_id, correlation)
    approval_id = _approval_id(client, seeded, run_id)

    response = client.post(
        f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
        json={"decision": "approved", "note": _SECRET_MARKER},
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 200, response.text
    assert _SECRET_MARKER not in response.text
    assert response.json()["status"] == "approved"

    approval = db.get(AutomationApproval, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.status is AutomationApprovalStatus.APPROVED
    assert str(approval.decided_by) == seeded.owner_a_id
    assert approval.decided_at is not None
    assert _audit_count(db, "automation.approval_decided") == 1


def test_rejection_has_no_sensitive_effects(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
) -> None:
    del queued, task_sessions
    rule_id = _ready_rule(
        client,
        seeded,
        actions=[
            {
                "type": "propose_stage_change",
                "payload": {"target_stage": "offer"},
            }
        ],
    )
    correlation = str(uuid.uuid4())
    run = _post_execution(
        client, seeded, rule_id, "run", key="decide-reject", correlation=correlation
    )
    run_id = str(run["id"])
    _execute_worker(seeded, run_id, correlation)
    approval_id = _approval_id(client, seeded, run_id)

    response = client.post(
        f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
        json={"decision": "rejected", "note": _SECRET_MARKER},
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 200, response.text
    assert response.json()["run_status"] == "cancelled"
    application = db.get(Application, uuid.UUID(seeded.application_id))
    assert application is not None
    assert application.stage is ApplicationStage.INTERVIEW
    assert _audit_count(db, "automation.run_cancelled") == 1


def test_cancel_reaches_terminal_status_once(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    del queued
    rule_id = _ready_rule(client, seeded)
    run = _post_execution(client, seeded, rule_id, "run", key="cancel-once")
    run_id = str(run["id"])

    response = client.post(f"{_URL}/runs/{run_id}/cancel", headers=_headers(seeded.org_a))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert _audit_count(db, "automation.run_cancelled") == 1

    repeated = client.post(
        f"{_URL}/runs/{run_id}/cancel", headers=_headers(seeded.org_a)
    )
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"
    assert _audit_count(db, "automation.run_cancelled") == 1


def test_reviewer_cannot_write(client: TestClient, seeded: _Seed) -> None:
    rule_id = _create_rule(client, seeded)
    _login(client, _REVIEWER)
    headers = _headers(seeded.org_a)

    created = client.post(_URL, json={"name": "Denied"}, headers=headers)
    assert created.status_code == 403
    patched = client.patch(
        f"{_URL}/{rule_id}", json={"status": "active"}, headers=headers
    )
    assert patched.status_code == 403
    tested = client.post(
        f"{_URL}/{rule_id}/test",
        json={
            "application_id": seeded.application_id,
            "idempotency_key": "reviewer-denied",
        },
        headers=headers,
    )
    assert tested.status_code == 403


def test_cross_tenant_resources_return_404(
    client: TestClient, seeded: _Seed, queued: list[tuple[object, ...]]
) -> None:
    del queued
    rule_id = _ready_rule(client, seeded)
    run = _post_execution(client, seeded, rule_id, "run", key="cross-tenant")
    run_id = str(run["id"])

    _login(client, _OWNER_B)
    headers = _headers(seeded.org_b)
    assert client.get(f"{_URL}/{rule_id}", headers=headers).status_code == 404
    assert client.get(f"{_URL}/runs/{run_id}", headers=headers).status_code == 404
    events = client.get(f"{_URL}/runs/{run_id}/events", headers=headers)
    assert events.status_code == 404
    approvals = client.get(f"{_URL}/runs/{run_id}/approvals", headers=headers)
    assert approvals.status_code == 404
    cancelled = client.post(f"{_URL}/runs/{run_id}/cancel", headers=headers)
    assert cancelled.status_code == 404


def test_missing_cookie_is_401_and_foreign_organization_is_403(
    client: TestClient, seeded: _Seed
) -> None:
    client.cookies.clear()
    response = client.post(
        _URL, json={"name": "Denied"}, headers=_headers(seeded.org_a)
    )
    assert response.status_code == 401

    _login(client, _OWNER_B)
    foreign = client.get(_URL, headers=_headers(seeded.org_a))
    assert foreign.status_code == 403


def test_invalid_decision_returns_400(
    client: TestClient,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
) -> None:
    del queued, task_sessions
    rule_id = _ready_rule(client, seeded)
    correlation = str(uuid.uuid4())
    run = _post_execution(
        client, seeded, rule_id, "run", key="invalid-decision", correlation=correlation
    )
    run_id = str(run["id"])
    _execute_worker(seeded, run_id, correlation)
    approval_id = _approval_id(client, seeded, run_id)

    for decision in ("maybe", "pending"):
        response = client.post(
            f"{_URL}/runs/{run_id}/approvals/{approval_id}/decide",
            json={"decision": decision},
            headers=_headers(seeded.org_a),
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "bad_request"


def test_run_events_expose_only_sanitized_metadata(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    del queued
    rule_id = _ready_rule(client, seeded)
    run = _post_execution(client, seeded, rule_id, "test", key="events-sanitized")
    run_id = str(run["id"])
    stored = db.get(AutomationRun, uuid.UUID(str(run_id)))
    assert stored is not None
    events = list_run_events(db, stored.organization_id, stored.id)
    assert any(
        event.event_type is AutomationRunEventType.TRIGGER_MATCHED for event in events
    )
    response = client.get(
        f"{_URL}/runs/{run_id}/events?limit=1&offset=0",
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] >= 1
    assert len(response.json()["items"]) == 1
    item = response.json()["items"][0]
    assert set(item) == {"event_type", "created_at", "correlation_id", "payload"}
    assert "organization_id" not in item["payload"]
    assert "note" not in item["payload"]
