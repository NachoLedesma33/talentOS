from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import email_validator
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents.models import AgentRun, AgentRunStatus, Approval, ApprovalStatus
from app.api.routes import agents as agents_routes
from app.applications.models import Application, ApplicationStage
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
from app.jobs.models import Job, JobStatus
from app.main import app

_URL = "/api/v1/agents/assistant"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME
_QUOTE = "Python confirmed"

_OWNER_A = "assistant-api-owner@example.test"
_OWNER_B = "assistant-api-foreign@example.test"
_VIEWER = "assistant-api-viewer@example.test"


@dataclass(frozen=True)
class Seed:
    org_a: str
    org_b: str
    owner_id: str
    document_id: uuid.UUID
    foreign_document_id: uuid.UUID


class _Provider:
    """Proveedor determinista; sin red y con salida validada por el grafo."""

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


class _SyncExecutor:
    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        del wait, cancel_futures
        return None


@contextmanager
def _sync_executor(_config: Any) -> Iterator[_SyncExecutor]:
    yield _SyncExecutor()


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture(autouse=True)
def _sync_langgraph_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "langgraph.pregel._executor.get_executor_for_config", _sync_executor
    )


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


def _login(client: TestClient, email: str, organization_id: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert _COOKIE in client.cookies
    response = client.get(
        "/api/v1/auth/me", headers={"X-Organization-ID": organization_id}
    )
    assert response.status_code == 200, response.text


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORGS_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _add_document(
    db: DBSession,
    organization_id: uuid.UUID,
    candidate_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    internal_name: str,
) -> Document:
    document = Document(
        organization_id=organization_id,
        candidate_id=candidate_id,
        uploaded_by=uploaded_by,
        original_filename="synthetic.txt",
        internal_name=internal_name,
        content_type="text/plain",
        extension="txt",
        size_bytes=len(_QUOTE),
        checksum_sha256="synthetic-checksum-" + internal_name,
        status=DocumentStatus.PROCESSED,
        page_count=1,
    )
    db.add(document)
    db.flush()
    extraction = DocumentExtraction(
        document_id=document.id,
        provider="mock",
        model="synthetic-model",
        prompt_version="extraction-v1",
        status=ExtractionStatus.COMPLETED,
        pages=[{"page": 1, "text": _QUOTE}],
    )
    db.add(extraction)
    db.flush()
    db.add(
        ExtractedField(
            extraction_id=extraction.id,
            field_name=ExtractedFieldName.SKILLS,
            value=_QUOTE,
            status=ExtractedFieldStatus.CONFIRMED,
            confirmed_by=uploaded_by,
            evidence=[
                {
                    "document_id": str(document.id),
                    "page": 1,
                    "quote": _QUOTE,
                    "offset": 0,
                }
            ],
        )
    )
    db.flush()
    return document


@pytest.fixture
def seeded(client: TestClient, db: DBSession) -> Seed:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Foreign Owner"),
        (_VIEWER, "Synthetic Viewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A, "")
    org_a = _create_org(client, "Assistant API Org A", "assistant-api-a")
    _login(client, _OWNER_A, org_a)
    response = client.post(
        f"{_ORGS_URL}/{org_a}/members",
        json={"email": _VIEWER, "role": "viewer"},
        headers={"X-Organization-ID": org_a},
    )
    assert response.status_code == 201, response.text

    _login(client, _OWNER_B, "")
    org_b = _create_org(client, "Assistant API Org B", "assistant-api-b")
    _login(client, _OWNER_B, org_b)

    user_ids = {
        row.email: str(row.id)
        for row in db.scalars(select(User)).all()
        if row.email in {_OWNER_A, _OWNER_B}
    }
    org_a_uuid = uuid.UUID(org_a)
    org_b_uuid = uuid.UUID(org_b)
    owner_a_id = uuid.UUID(user_ids[_OWNER_A])
    owner_b_id = uuid.UUID(user_ids[_OWNER_B])
    candidate_a = Candidate(
        organization_id=org_a_uuid,
        name="Synthetic Candidate A",
        email="assistant-api-candidate@example.test",
    )
    candidate_b = Candidate(
        organization_id=org_b_uuid,
        name="Foreign Candidate",
        email="assistant-api-foreign-candidate@example.test",
    )
    db.add_all([candidate_a, candidate_b])
    db.flush()
    for organization_id, owner_id in (
        (org_a_uuid, owner_a_id),
        (org_b_uuid, owner_b_id),
    ):
        db.add(
            Job(
                organization_id=organization_id,
                owner_id=owner_id,
                title="Synthetic role",
                description="Synthetic job",
                status=JobStatus.OPEN,
            )
        )
    db.flush()
    job_a = db.scalars(
        select(Job).where(Job.organization_id == org_a_uuid)
    ).one()
    job_b = db.scalars(
        select(Job).where(Job.organization_id == org_b_uuid)
    ).one()
    db.add_all(
        [
            Application(
                organization_id=org_a_uuid,
                job_id=job_a.id,
                candidate_id=candidate_a.id,
                stage=ApplicationStage.APPLIED,
            ),
            Application(
                organization_id=org_b_uuid,
                job_id=job_b.id,
                candidate_id=candidate_b.id,
                stage=ApplicationStage.APPLIED,
            ),
        ]
    )
    db.flush()
    document = _add_document(db, org_a_uuid, candidate_a.id, owner_a_id, "assistant-api-doc")
    foreign_document = _add_document(
        db, org_b_uuid, candidate_b.id, owner_b_id, "assistant-api-foreign-doc"
    )
    db.commit()
    _login(client, _OWNER_A, org_a)
    return Seed(
        org_a=org_a,
        org_b=org_b,
        owner_id=user_ids[_OWNER_A],
        document_id=document.id,
        foreign_document_id=foreign_document.id,
    )


@pytest.fixture
def runtime(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, seeded: Seed
) -> _Provider:
    del seeded
    provider = _Provider(_output())
    monkeypatch.setattr(agents_routes, "get_llm_provider", lambda: provider)
    monkeypatch.setattr(
        agents_routes,
        "SessionLocal",
        lambda: DBSession(engine, expire_on_commit=False),
    )
    return provider


def _output(
    *,
    document_id: uuid.UUID | None = None,
    with_citation: bool = True,
    actions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    citations: list[dict[str, object]] = []
    if with_citation and document_id is not None:
        citations.append(
            {"document_id": str(document_id), "quote": _QUOTE, "page": 1}
        )
    return {
        "answer": "Synthetic verified answer",
        "citations": citations,
        "actions": actions or [],
        "limitations": [],
        "needs_review": False,
    }


def _headers(seed: Seed) -> dict[str, str]:
    return {"X-Organization-ID": seed.org_a}


def _message(
    key: str,
    *,
    resource_ref: uuid.UUID | None = None,
    message: str = "¿Qué skills confirma el CV?",
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "message": message,
        "surface": "dashboard",
        "resource_ref": None if resource_ref is None else str(resource_ref),
        "recent_messages": [],
        "idempotency_key": key,
    }


def _post_message(
    client: TestClient, seed: Seed, payload: dict[str, object]
) -> Any:
    return client.post(f"{_URL}/messages", json=payload, headers=_headers(seed))


def test_message_requires_session(client: TestClient, seeded: Seed) -> None:
    client.cookies.clear()
    response = _post_message(client, seeded, _message("assistant-api-no-session"))
    assert response.status_code == 401


def test_message_returns_verified_citation_and_is_idempotent(
    client: TestClient, seeded: Seed, runtime: _Provider
) -> None:
    payload = _message("assistant-api-verified", resource_ref=seeded.document_id)
    runtime.output = _output(document_id=seeded.document_id)
    first = _post_message(client, seeded, payload)

    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "completed"
    assert body["answer"] == "Synthetic verified answer"
    assert body["citations"][0]["document_id"] == str(seeded.document_id)
    assert body["citations"][0]["quote"] == _QUOTE

    second = _post_message(client, seeded, payload)

    assert second.status_code == 200, second.text
    assert second.json()["run_id"] == body["run_id"]
    assert runtime.calls == 1


def test_foreign_resource_ref_is_not_available_without_revealing_it(
    client: TestClient, seeded: Seed, runtime: _Provider
) -> None:
    response = _post_message(
        client,
        seeded,
        _message(
            "assistant-api-foreign",
            resource_ref=seeded.foreign_document_id,
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["unsupported_reason"] == "not_available"
    assert body["citations"] == []
    assert runtime.calls == 0
    assert str(seeded.foreign_document_id) not in response.text


def test_viewer_can_explain_but_cannot_request_draft_actions(
    client: TestClient, seeded: Seed, runtime: _Provider
) -> None:
    runtime.output = _output(
        with_citation=False,
        actions=[{"type": "create_draft", "form_id": "message.draft"}],
    )
    _login(client, _VIEWER, seeded.org_a)
    response = _post_message(client, seeded, _message("assistant-api-viewer"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "needs_review"
    assert body["proposed_actions"] == []
    assert "permission_denied" in body["limitations"]


def test_waits_for_approval_and_ack_applies_only_after_decision(
    client: TestClient, seeded: Seed, runtime: _Provider, db: DBSession
) -> None:
    runtime.output = _output(
        with_citation=False, actions=[{"type": "navigate", "route": "/jobs"}]
    )
    created = _post_message(client, seeded, _message("assistant-api-approval"))

    assert created.status_code == 201, created.text
    waiting = created.json()
    assert waiting["status"] == "waiting_approval"
    assert len(waiting["proposed_actions"]) == 1
    action_id = waiting["proposed_actions"][0]["action_id"]
    db.expire_all()
    approvals = db.scalars(select(Approval)).all()
    assert len(approvals) == 1
    assert approvals[0].status is ApprovalStatus.PENDING

    ack = client.post(
        f"{_URL}/actions/{action_id}/ack",
        json={
            "schema_version": "1.0",
            "action_id": action_id,
            "decision": "applied",
            "idempotency_key": "assistant-api-approval",
        },
        headers=_headers(seeded),
    )

    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "completed"
    db.expire_all()
    approval = db.scalars(select(Approval)).one()
    assert approval.status is ApprovalStatus.APPROVED
    assert str(approval.decided_by) == seeded.owner_id
    run = db.get(AgentRun, uuid.UUID(waiting["run_id"]))
    assert run is not None
    assert run.status is AgentRunStatus.COMPLETED

    repeated = client.post(
        f"{_URL}/actions/{action_id}/ack",
        json={
            "schema_version": "1.0",
            "action_id": action_id,
            "decision": "applied",
            "idempotency_key": "assistant-api-approval",
        },
        headers=_headers(seeded),
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["status"] == "completed"


def test_ack_for_unknown_action_does_not_resume_approval(
    client: TestClient, seeded: Seed, runtime: _Provider, db: DBSession
) -> None:
    runtime.output = _output(
        with_citation=False, actions=[{"type": "navigate", "route": "/jobs"}]
    )
    created = _post_message(client, seeded, _message("assistant-api-unknown-action"))

    assert created.status_code == 201, created.text
    unknown_id = uuid.uuid4()
    ack = client.post(
        f"{_URL}/actions/{unknown_id}/ack",
        json={
            "schema_version": "1.0",
            "action_id": str(unknown_id),
            "decision": "applied",
            "idempotency_key": "assistant-api-unknown-action",
        },
        headers=_headers(seeded),
    )

    assert ack.status_code == 404
    db.expire_all()
    approval = db.scalars(select(Approval)).one()
    assert approval.status is ApprovalStatus.PENDING
    assert approval.decided_at is None

    assert datetime.now(UTC).tzinfo is not None
