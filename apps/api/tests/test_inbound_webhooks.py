"""Tests de integración de webhooks entrantes.

SQLite aislada, firma HMAC real sobre cuerpo crudo, cola y reloj controlados,
clave Fernet efímera y datos sintéticos. Sin Docker, red ni CV reales.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn

import email_validator
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, func, inspect, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.automation.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.integrations.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.audit.models import AuditLog
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.integrations import service as integrations_service
from app.integrations import tasks as webhook_tasks
from app.integrations.models import (
    Integration,
    WebhookEvent,
    WebhookEventStatus,
)
from app.main import app

_URL = "/api/v1/webhooks"
_INTEGRATIONS_URL = "/api/v1/integrations"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-webhooks@example.test"
_OWNER_B = "owner-b-webhooks@example.test"
_VIEWER = "viewer-webhooks@example.test"
_SECRET = "SyntheticInboundSecretDoNotExpose123"
_CV_MARKER = "SyntheticCvMarkerDoNotExpose"
_BROKER_MARKER = "SyntheticBrokerMarkerDoNotExpose"


class _RetryCaptured(Exception):
    def __init__(self, countdown: int) -> None:
        self.countdown = countdown
        super().__init__("retry captured")


@dataclass(frozen=True)
class _Seed:
    org_a: str
    org_b: str


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture(autouse=True)
def _talentos_logger_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Alembic `fileConfig` de otras pruebas puede desactivar el logger global.
    monkeypatch.setattr(logging.getLogger("talentos"), "disabled", False)


@pytest.fixture(autouse=True)
def _integration_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    """Captura el contexto encolado sin broker real."""
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        webhook_tasks.process_webhook_event,
        "delay",
        lambda *args: calls.append(args),
    )
    return calls


@pytest.fixture
def task_sessions(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """La tarea abre su propia sesión contra la SQLite aislada del test."""
    monkeypatch.setattr(
        webhook_tasks,
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


def _org_headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


@pytest.fixture
def seeded(client: TestClient) -> _Seed:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Owner B"),
        (_VIEWER, "Synthetic Viewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Webhooks Org A", "webhooks-org-a")
    response = client.post(
        f"{_ORGS_URL}/{org_a}/members",
        json={"email": _VIEWER, "role": "viewer"},
        headers=_org_headers(org_a),
    )
    assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Webhooks Org B", "webhooks-org-b")

    _login(client, _OWNER_A)
    return _Seed(org_a=org_a, org_b=org_b)


def _create_inbound(client: TestClient, seed: _Seed) -> dict[str, object]:
    response = client.post(
        _INTEGRATIONS_URL,
        json={
            "provider": "webhook_inbound",
            "config": {"secret": _SECRET, "tolerance_seconds": 300},
        },
        headers=_org_headers(seed.org_a),
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


def _iso(offset_seconds: int = 0) -> str:
    value = datetime.now(UTC) + timedelta(seconds=offset_seconds)
    return value.isoformat().replace("+00:00", "Z")


def _body(
    organization_id: str,
    *,
    event_id: uuid.UUID | None = None,
    event_type: str = "candidate.created",
    occurred_at: str | None = None,
    correlation_id: uuid.UUID | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": event_type,
        "organization_id": organization_id,
        "occurred_at": occurred_at or _iso(),
        "resource_id": str(uuid.uuid4()),
        "correlation_id": str(correlation_id or uuid.uuid4()),
        "payload_version": "1",
        "payload": payload if payload is not None else {"kind": "synthetic"},
    }


def _raw(body: dict[str, object]) -> bytes:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _signature(raw_body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _signature_headers(
    key_id: str, event_id: str, timestamp: str, signature: str
) -> dict[str, str]:
    return {
        "X-TalentOS-Key-ID": key_id,
        "X-TalentOS-Event-ID": event_id,
        "X-TalentOS-Timestamp": timestamp,
        "X-TalentOS-Signature": signature,
    }


def _post(
    client: TestClient,
    integration_id: str,
    key_id: str,
    body: dict[str, object],
    *,
    secret: str = _SECRET,
    timestamp: str | None = None,
    signature: str | None = None,
) -> tuple[object, bytes, str]:
    raw_body = _raw(body)
    used_signature = signature if signature is not None else _signature(raw_body, secret)
    response = client.post(
        f"{_URL}/inbound/{integration_id}",
        content=raw_body,
        headers=_signature_headers(
            key_id, str(body["event_id"]), timestamp or _iso(), used_signature
        ),
    )
    return response, raw_body, used_signature


def _event_count(db: DBSession) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(WebhookEvent)) or 0)


def _get_event(db: DBSession, event_id: uuid.UUID) -> WebhookEvent:
    db.expire_all()
    event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    assert event is not None
    return event


def _audit_count(db: DBSession, action: str) -> int:
    db.expire_all()
    return int(
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
        or 0
    )


def _install_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    def _raise_transient(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError(_BROKER_MARKER)

    retries: list[int] = []

    def _retry(*, exc: object, countdown: int) -> NoReturn:
        assert exc is not None
        retries.append(countdown)
        raise _RetryCaptured(countdown)

    monkeypatch.setattr(integrations_service, "process_webhook_event", _raise_transient)
    monkeypatch.setattr(webhook_tasks.process_webhook_event, "retry", _retry)
    return retries


def test_valid_signature_accepts_once_audits_and_enqueues_context(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    assert _event_count(db) == 0
    body = _body(seeded.org_a)

    response, _raw_body, _signature_value = _post(
        client,
        str(integration["id"]),
        str(integration["key_id"]),
        body,
    )

    assert response.status_code == 202, response.text
    result = response.json()
    assert set(result) == {"event_id", "correlation_id", "status", "duplicate"}
    assert result == {
        "event_id": body["event_id"],
        "correlation_id": body["correlation_id"],
        "status": "queued",
        "duplicate": False,
    }
    assert _event_count(db) == 1
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    assert event.status is WebhookEventStatus.QUEUED
    assert len(event.payload_hash) == 64
    assert queued == [
        (
            seeded.org_a,
            str(integration["id"]),
            str(body["event_id"]),
            str(body["correlation_id"]),
        )
    ]
    assert _audit_count(db, "webhook.received") == 1


def test_invalid_signature_and_modified_body_have_no_effect(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    raw_body = _raw(body)
    integration_id = str(integration["id"])
    key_id = str(integration["key_id"])
    event_id = str(body["event_id"])

    bad_signature = client.post(
        f"{_URL}/inbound/{integration_id}",
        content=raw_body,
        headers=_signature_headers(key_id, event_id, _iso(), f"sha256={'0' * 64}"),
    )
    assert bad_signature.status_code == 401, bad_signature.text

    tampered = dict(body)
    tampered["payload"] = {"kind": "tampered"}
    response = client.post(
        f"{_URL}/inbound/{integration_id}",
        content=_raw(tampered),
        headers=_signature_headers(key_id, event_id, _iso(), _signature(raw_body)),
    )
    assert response.status_code == 401, response.text

    assert _event_count(db) == 0
    assert _audit_count(db, "webhook.received") == 0
    assert queued == []


def test_unknown_key_id_is_rejected(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)

    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), "000000000000", body
    )

    assert response.status_code == 401, response.text
    assert _event_count(db) == 0
    assert queued == []


@pytest.mark.parametrize(
    ("offset_seconds", "expected_status"),
    [(-600, 400), (120, 202), (600, 400)],
)
def test_timestamp_tolerance_rejects_stale_and_far_future(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    offset_seconds: int,
    expected_status: int,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)

    response, _raw_body, _signature_value = _post(
        client,
        str(integration["id"]),
        str(integration["key_id"]),
        body,
        timestamp=_iso(offset_seconds),
    )

    assert response.status_code == expected_status, response.text
    assert _event_count(db) == (1 if expected_status == 202 else 0)
    assert len(queued) == (1 if expected_status == 202 else 0)


def test_replay_returns_duplicate_without_second_effect(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)

    first, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    second, _raw_again, _signature_again = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )

    assert first.status_code == 202, first.text
    assert first.json()["duplicate"] is False
    assert second.status_code == 202, second.text
    assert second.json() == {
        "event_id": body["event_id"],
        "correlation_id": body["correlation_id"],
        "status": "queued",
        "duplicate": True,
    }
    assert _event_count(db) == 1
    assert _audit_count(db, "webhook.received") == 1
    assert len(queued) == 1


def test_envelope_from_another_tenant_is_rejected_without_effect(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_b)

    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )

    assert response.status_code == 400, response.text
    assert _event_count(db) == 0
    assert queued == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("event_type", "unknown.event"), ("extra_field", "unexpected")],
)
def test_unknown_event_type_and_extra_fields_are_rejected(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    field: str,
    value: object,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    body[field] = value

    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )

    assert response.status_code == 400, response.text
    assert _event_count(db) == 0
    assert queued == []


def test_forbidden_payload_key_is_rejected(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a, payload={"cv": _CV_MARKER})

    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )

    assert response.status_code == 400, response.text
    assert _event_count(db) == 0


def test_broker_failure_keeps_evidence_and_returns_503(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)

    def _broker_down(*_args: object) -> None:
        raise RuntimeError(_BROKER_MARKER)

    monkeypatch.setattr(webhook_tasks.process_webhook_event, "delay", _broker_down)
    with caplog.at_level(logging.INFO, logger="talentos"):
        response, _raw_body, _signature_value = _post(
            client, str(integration["id"]), str(integration["key_id"]), body
        )

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "service_unavailable"
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    assert event.status is WebhookEventStatus.ENQUEUE_FAILED
    assert event.last_error_code == "broker_unavailable"
    assert _audit_count(db, "webhook.received") == 1
    assert _BROKER_MARKER not in caplog.text
    assert "Traceback" not in caplog.text


def test_task_processes_event_and_audits_without_payload(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    assert response.status_code == 202, response.text

    webhook_tasks.process_webhook_event(
        seeded.org_a,
        str(integration["id"]),
        str(body["event_id"]),
        str(body["correlation_id"]),
    )

    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    assert event.status is WebhookEventStatus.PROCESSED
    assert event.last_error_code is None
    assert event.attempts == 0
    assert _audit_count(db, "webhook.processed") == 1


def test_task_rejects_foreign_organization_and_correlation(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    assert response.status_code == 202, response.text

    with caplog.at_level(logging.WARNING, logger="talentos"):
        webhook_tasks.process_webhook_event(
            seeded.org_b,
            str(integration["id"]),
            str(body["event_id"]),
            str(body["correlation_id"]),
        )
        webhook_tasks.process_webhook_event(
            seeded.org_a,
            str(integration["id"]),
            str(body["event_id"]),
            str(uuid.uuid4()),
        )

    assert "organization_mismatch" in caplog.text
    assert "correlation_mismatch" in caplog.text
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    assert event.status is WebhookEventStatus.QUEUED
    assert _audit_count(db, "webhook.processed") == 0


@pytest.mark.parametrize(
    ("initial_attempts", "expected_countdown"),
    [(0, 2), (1, 4), (2, 8)],
)
def test_transient_failure_retries_with_bounded_exponential_backoff(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    initial_attempts: int,
    expected_countdown: int,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    assert response.status_code == 202, response.text
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    event.attempts = initial_attempts
    db.commit()

    retries = _install_transient_failure(monkeypatch)
    with pytest.raises(_RetryCaptured) as captured:
        webhook_tasks.process_webhook_event(
            seeded.org_a,
            str(integration["id"]),
            str(body["event_id"]),
            str(body["correlation_id"]),
        )

    assert captured.value.countdown == expected_countdown
    assert retries == [expected_countdown]
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    assert event.status is WebhookEventStatus.FAILED
    assert event.attempts == initial_attempts + 1
    assert event.last_error_code == "transient_processing_failure"


def test_exhausted_retries_go_to_dead_letter_without_trace(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    task_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    assert response.status_code == 202, response.text
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    event.attempts = 3
    db.commit()

    retries = _install_transient_failure(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="talentos"):
        webhook_tasks.process_webhook_event(
            seeded.org_a,
            str(integration["id"]),
            str(body["event_id"]),
            str(body["correlation_id"]),
        )

    assert retries == []
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    assert event.status is WebhookEventStatus.DEAD_LETTER
    assert event.attempts == 4
    assert event.last_error_code == "max_retries_exceeded"
    assert _BROKER_MARKER not in caplog.text
    assert "Traceback" not in caplog.text


def test_manual_retry_owner_succeeds_and_viewer_is_forbidden(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    assert response.status_code == 202, response.text
    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    event.status = WebhookEventStatus.DEAD_LETTER
    event.attempts = 4
    event.last_error_code = "max_retries_exceeded"
    db.commit()
    retry_url = (
        f"{_INTEGRATIONS_URL}/{integration['id']}/webhooks/{body['event_id']}/retry"
    )

    queued_before = list(queued)
    _login(client, _VIEWER)
    forbidden = client.post(retry_url, headers=_org_headers(seeded.org_a))
    assert forbidden.status_code == 403, forbidden.text
    assert queued == queued_before

    _login(client, _OWNER_A)
    allowed = client.post(retry_url, headers=_org_headers(seeded.org_a))
    assert allowed.status_code == 202, allowed.text
    result = allowed.json()
    assert set(result) == {
        "id",
        "event_id",
        "event_type",
        "status",
        "attempts",
        "last_error_code",
        "occurred_at",
        "received_at",
    }
    assert result["status"] == "queued"
    assert result["attempts"] == 0
    assert result["last_error_code"] is None
    assert len(queued) == len(queued_before) + 1
    assert _audit_count(db, "webhook.retry_requested") == 1


def test_manual_retry_rejects_queued_event(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(seeded.org_a)
    response, _raw_body, _signature_value = _post(
        client, str(integration["id"]), str(integration["key_id"]), body
    )
    assert response.status_code == 202, response.text

    retry = client.post(
        f"{_INTEGRATIONS_URL}/{integration['id']}/webhooks/{body['event_id']}/retry",
        headers=_org_headers(seeded.org_a),
    )

    assert retry.status_code == 409, retry.text
    assert queued == [queued[0]] if queued else True
    assert _audit_count(db, "webhook.retry_requested") == 0


def test_no_secret_signature_raw_body_or_cv_in_logs_or_database(
    client: TestClient,
    db: DBSession,
    engine: Engine,
    seeded: _Seed,
    queued: list[tuple[object, ...]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration = _create_inbound(client, seeded)
    body = _body(
        seeded.org_a,
        payload={"summary": f"Synthetic summary with {_CV_MARKER}"},
    )

    with caplog.at_level(logging.INFO, logger="talentos"):
        response, raw_body, signature = _post(
            client, str(integration["id"]), str(integration["key_id"]), body
        )
    assert response.status_code == 202, response.text

    event = _get_event(db, uuid.UUID(str(body["event_id"])))
    stored = str(vars(event))
    columns = {column["name"] for column in inspect(engine).get_columns("webhook_events")}
    for forbidden in (_SECRET, signature, raw_body.decode("utf-8"), _CV_MARKER):
        assert forbidden not in caplog.text
        assert forbidden not in stored
        assert forbidden not in response.text
    assert not {"raw_body", "payload", "secret", "signature"} & columns
    assert "gAAAAA" not in stored
    integration_row = dict(db.execute(select(Integration.__table__)).one()._mapping)
    for forbidden in (_SECRET, signature, raw_body.decode("utf-8"), _CV_MARKER):
        assert forbidden not in str(integration_row)
