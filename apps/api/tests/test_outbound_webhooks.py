"""Tests de webhooks salientes firmados, outbox, reintentos y reintento manual.

SQLite aislada, datos sintéticos, clave Fernet efímera, sender determinista y
httpx.MockTransport sin red. Sin CV, secretos reales ni decisiones automáticas.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

import email_validator
import httpx
import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, func, inspect, select, text
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
from app.identity.models import User
from app.integrations import service as integrations_service
from app.integrations import tasks as webhook_tasks
from app.integrations.models import WebhookDelivery, WebhookDeliveryStatus
from app.integrations.outbound import (
    HttpxWebhookSender,
    StubWebhookSender,
    WebhookDeliveryResult,
)
from app.integrations.schemas import OutboundEventRequest
from app.integrations.webhooks import parse_timestamp
from app.main import app

_URL = "/api/v1/integrations"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-outbound@example.test"
_OWNER_B = "owner-b-outbound@example.test"
_VIEWER = "viewer-outbound@example.test"
_SECRET_A = "SyntheticOutboundSecretDoNotExpose123"
_SECRET_B = "SyntheticRotatedSecretDoNotExpose456"
_ENDPOINT_A = "https://hooks.outbound.example.test/sink"
_QUERY_SECRET = "QuerySecretMarkerDoNotExpose"
_CV_MARKER = "SyntheticCvMarkerDoNotExpose"
_EMAIL_MARKER = "candidate-outbound@example.test"
_TOKEN_MARKER = "SyntheticTokenMarkerDoNotExpose"
_PAYLOAD_MARKER = "SyntheticPayloadStage"


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
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        webhook_tasks.deliver_webhook,
        "delay",
        lambda *args: calls.append(args),
    )
    return calls


@pytest.fixture
def task_sessions(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webhook_tasks,
        "SessionLocal",
        lambda: DBSession(engine, expire_on_commit=False),
    )


@pytest.fixture
def stub_sender(monkeypatch: pytest.MonkeyPatch) -> StubWebhookSender:
    sender = StubWebhookSender()
    monkeypatch.setattr(integrations_service, "HttpxWebhookSender", lambda: sender)
    return sender


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
def seeded(client: TestClient) -> _Seed:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Owner B"),
        (_VIEWER, "Synthetic Viewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Outbound Org A", "outbound-org-a")
    response = client.post(
        f"{_ORGS_URL}/{org_a}/members",
        json={"email": _VIEWER, "role": "viewer"},
        headers=_headers(org_a),
    )
    assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Outbound Org B", "outbound-org-b")

    _login(client, _OWNER_A)
    return _Seed(org_a=org_a, org_b=org_b)


def _create_integration(
    client: TestClient,
    seed: _Seed,
    *,
    secret: str = _SECRET_A,
    endpoint: str = _ENDPOINT_A,
) -> dict[str, object]:
    response = client.post(
        _URL,
        json={
            "provider": "webhook_outbound",
            "config": {"endpoint": endpoint, "secret": secret},
        },
        headers=_headers(seed.org_a),
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


def _owner_id(db: DBSession) -> uuid.UUID:
    user = db.scalar(select(User).where(User.email == _OWNER_A))
    assert user is not None
    return user.id


def _create_delivery(
    db: DBSession,
    seed: _Seed,
    integration_id: uuid.UUID,
    *,
    event_id: uuid.UUID | None = None,
    payload: dict[str, object] | None = None,
) -> WebhookDelivery:
    return integrations_service.create_outbound_event(
        db,
        organization_id=uuid.UUID(seed.org_a),
        actor_id=_owner_id(db),
        actor_role="owner",
        integration_id=integration_id,
        event_id=event_id or uuid.uuid4(),
        event_type="application.stage_changed",
        resource_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        payload=payload if payload is not None else {"stage": _PAYLOAD_MARKER},
    )


def _count_deliveries(db: DBSession) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(WebhookDelivery)) or 0)


def _refresh(db: DBSession, delivery: WebhookDelivery) -> WebhookDelivery:
    db.refresh(delivery)
    return delivery


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _audit_count(db: DBSession, action: str) -> int:
    db.expire_all()
    return int(
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
        or 0
    )


def _db_text(db: DBSession) -> str:
    rows = db.execute(text("SELECT * FROM webhook_deliveries")).all()
    return str([tuple(str(value) for value in row) for row in rows])


def test_outbox_uses_caller_transaction_and_unique_event_id(
    engine: Engine, client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    integration_id = uuid.UUID(str(integration["id"]))
    event_id = uuid.uuid4()
    statements: list[str] = []

    def _capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append(statement.upper())

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        first = _create_delivery(db, seeded, integration_id, event_id=event_id)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert _count_deliveries(db) == 1
    assert first.status is WebhookDeliveryStatus.PENDING
    assert not any("COMMIT" in statement for statement in statements)

    created = _create_delivery(db, seeded, integration_id, event_id=event_id)
    db.commit()
    duplicate = _create_delivery(db, seeded, integration_id, event_id=event_id)
    db.commit()

    assert duplicate.id == created.id
    assert _count_deliveries(db) == 1
    assert _audit_count(db, "webhook_outbound.queued") == 1


def test_payload_is_bounded_sanitized_and_markers_are_rejected(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    integration_id = uuid.UUID(str(integration["id"]))
    payload = {"stage": _PAYLOAD_MARKER, "attempt": 1}

    delivery = _create_delivery(db, seeded, integration_id, payload=payload)
    db.commit()
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert delivery.payload_hash == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(ValidationError):
        OutboundEventRequest.model_validate(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "application.stage_changed",
                "resource_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4()),
                "payload": {"stage": "screening"},
                "extra": "unexpected",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"cv": _CV_MARKER},
        {"token": _TOKEN_MARKER},
        {"email": _EMAIL_MARKER},
        {"personal_email": _EMAIL_MARKER},
        {"note": _EMAIL_MARKER},
    ],
)
def test_cv_token_and_email_markers_are_rejected(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    payload: dict[str, object],
) -> None:
    integration = _create_integration(client, seeded)

    with pytest.raises(integrations_service.IntegrationServiceError) as exc:
        _create_delivery(db, seeded, uuid.UUID(str(integration["id"])), payload=payload)

    assert exc.value.code == "invalid_outbound_payload"
    assert _count_deliveries(db) == 0


def test_signed_body_matches_hmac_and_headers_carry_context(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()
    sender = StubWebhookSender([WebhookDeliveryResult(200, None)])

    outcome = integrations_service.deliver_webhook(db, delivery.id, sender=sender)
    db.commit()

    assert outcome == "delivered"
    assert len(sender.calls) == 1
    call = sender.calls[0]
    assert call.endpoint == _ENDPOINT_A
    expected = hmac.new(_SECRET_A.encode("utf-8"), call.body, hashlib.sha256).hexdigest()
    assert call.headers["X-TalentOS-Signature"] == f"sha256={expected}"
    assert call.headers["X-TalentOS-Key-ID"] == integration["key_id"]
    assert call.headers["X-TalentOS-Event-ID"] == str(delivery.event_id)
    assert call.headers["X-TalentOS-Correlation-ID"] == str(delivery.correlation_id)
    assert call.headers["Content-Type"] == "application/json"
    timestamp = parse_timestamp(call.headers["X-TalentOS-Timestamp"])
    assert abs((datetime.now(UTC) - timestamp).total_seconds()) <= 60

    body = json.loads(call.body)
    assert body["event_id"] == str(delivery.event_id)
    assert body["organization_id"] == seeded.org_a
    assert body["event_type"] == "application.stage_changed"
    assert body["resource_id"] == str(delivery.resource_id)
    assert body["correlation_id"] == str(delivery.correlation_id)
    assert body["payload_version"] == "1"
    assert _CV_MARKER not in call.body.decode("utf-8")


def test_success_marks_delivered_and_audits(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()
    sender = StubWebhookSender([WebhookDeliveryResult(204, None)])

    outcome = integrations_service.deliver_webhook(db, delivery.id, sender=sender)
    db.commit()
    refreshed = _refresh(db, delivery)

    assert outcome == "delivered"
    assert refreshed.status is WebhookDeliveryStatus.DELIVERED
    assert refreshed.delivered_at is not None
    assert refreshed.last_status_code == 204
    assert refreshed.next_attempt_at is None
    assert _audit_count(db, "webhook_outbound.delivered") == 1


def test_transient_failures_retry_exponentially_then_dead_letter(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()
    sender = StubWebhookSender(
        [
            WebhookDeliveryResult(503, "provider_rejected"),
            WebhookDeliveryResult(None, "provider_timeout"),
            WebhookDeliveryResult(500, "provider_rejected"),
        ]
    )

    expected_delays = (2, 4)
    for attempt, expected_delay in enumerate(expected_delays, start=1):
        before = datetime.now(UTC)
        outcome = integrations_service.deliver_webhook(db, delivery.id, sender=sender)
        db.commit()
        refreshed = _refresh(db, delivery)
        assert outcome == "retry_scheduled"
        assert refreshed.status is WebhookDeliveryStatus.FAILED
        assert refreshed.attempts == attempt
        assert refreshed.next_attempt_at is not None
        delay = (_as_utc(refreshed.next_attempt_at) - before).total_seconds()
        assert expected_delay - 1 <= delay <= expected_delay + 1

    outcome = integrations_service.deliver_webhook(db, delivery.id, sender=sender)
    db.commit()
    refreshed = _refresh(db, delivery)

    assert outcome == "dead_letter"
    assert refreshed.status is WebhookDeliveryStatus.DEAD_LETTER
    assert refreshed.attempts == 3
    assert refreshed.next_attempt_at is None
    assert refreshed.last_error_code == "provider_rejected"
    assert len(sender.calls) == 3


def test_non_transient_4xx_dead_letters_without_retry(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()
    sender = StubWebhookSender([WebhookDeliveryResult(400, "provider_rejected")])

    outcome = integrations_service.deliver_webhook(db, delivery.id, sender=sender)
    db.commit()
    refreshed = _refresh(db, delivery)

    assert outcome == "dead_letter"
    assert refreshed.status is WebhookDeliveryStatus.DEAD_LETTER
    assert refreshed.attempts == 1
    assert refreshed.next_attempt_at is None
    assert refreshed.last_status_code == 400
    assert _audit_count(db, "webhook_outbound.delivered") == 0


def test_config_rotation_changes_key_id_and_signature(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration = _create_integration(client, seeded)
    integration_id = str(integration["id"])
    first = _create_delivery(db, seeded, uuid.UUID(integration_id))
    first_sender = StubWebhookSender([WebhookDeliveryResult(200, None)])
    integrations_service.deliver_webhook(db, first.id, sender=first_sender)
    db.commit()
    first_signature = first_sender.calls[0].headers["X-TalentOS-Signature"]

    # Rotación de clave de cifrado (ADR-013): cambia key_id y el token cifrado.
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    get_settings.cache_clear()
    response = client.patch(
        f"{_URL}/{integration_id}",
        json={
            "config": {"endpoint": _ENDPOINT_A, "secret": _SECRET_B},
            "expected_version": 1,
        },
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 200, response.text
    rotated = response.json()

    second = _create_delivery(db, seeded, uuid.UUID(integration_id))
    second_sender = StubWebhookSender([WebhookDeliveryResult(200, None)])
    integrations_service.deliver_webhook(db, second.id, sender=second_sender)
    db.commit()
    second_signature = second_sender.calls[0].headers["X-TalentOS-Signature"]

    assert rotated["key_id"] != integration["key_id"]
    assert second_sender.calls[0].headers["X-TalentOS-Key-ID"] == rotated["key_id"]
    assert second_signature != first_signature


def test_manual_retry_owner_succeeds_and_viewer_is_forbidden(
    client: TestClient, db: DBSession, seeded: _Seed, queued: list[tuple[object, ...]]
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    delivery.status = WebhookDeliveryStatus.DEAD_LETTER
    delivery.attempts = 3
    delivery.last_error_code = "provider_timeout"
    db.commit()
    url = f"{_URL}/{integration['id']}/deliveries/{delivery.id}/retry"

    _login(client, _VIEWER)
    forbidden = client.post(url, headers=_headers(seeded.org_a))
    assert forbidden.status_code == 403, forbidden.text

    _login(client, _OWNER_A)
    allowed = client.post(url, headers=_headers(seeded.org_a))
    assert allowed.status_code == 202, allowed.text
    result = allowed.json()
    assert set(result) == {
        "id",
        "event_id",
        "event_type",
        "status",
        "attempts",
        "last_error_code",
        "last_status_code",
        "created_at",
        "delivered_at",
    }
    refreshed = _refresh(db, delivery)
    assert result["status"] == "pending"
    assert result["attempts"] == 3
    assert result["last_error_code"] == "provider_timeout"
    assert refreshed.status is WebhookDeliveryStatus.PENDING
    assert refreshed.next_attempt_at is None
    assert len(queued) == 1
    assert queued[0] == (
        str(delivery.id),
        seeded.org_a,
        str(delivery.correlation_id),
    )
    assert _audit_count(db, "webhook_outbound.retry_requested") == 1


def test_cross_tenant_list_retry_and_deliver_do_not_reveal_existence(
    client: TestClient, db: DBSession, seeded: _Seed, queued: list[tuple[object, ...]]
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()
    base = f"{_URL}/{integration['id']}"

    _login(client, _OWNER_B)
    listed = client.get(f"{base}/deliveries", headers=_headers(seeded.org_b))
    assert listed.status_code == 404, listed.text

    with pytest.raises(integrations_service.IntegrationDomainError) as exc:
        integrations_service.deliver_webhook(
            db,
            delivery.id,
            organization_id=uuid.UUID(seeded.org_b),
            sender=StubWebhookSender(),
        )
    assert exc.value.code == "webhook_delivery_not_found"
    assert _refresh(db, delivery).status is WebhookDeliveryStatus.PENDING

    retried = client.post(
        f"{base}/deliveries/{delivery.id}/retry", headers=_headers(seeded.org_b)
    )
    assert retried.status_code == 404, retried.text
    assert queued == []
    assert _audit_count(db, "webhook_outbound.retry_requested") == 0


def test_list_filters_by_status_and_never_returns_payload(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration = _create_integration(client, seeded)
    integration_id = str(integration["id"])
    pending = _create_delivery(db, seeded, uuid.UUID(integration_id))
    failed = _create_delivery(db, seeded, uuid.UUID(integration_id))
    failed.status = WebhookDeliveryStatus.FAILED
    db.commit()

    response = client.get(
        f"{_URL}/{integration_id}/deliveries",
        params={"status": "failed", "limit": 10},
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(failed.id)]
    assert set(body["items"][0]) == {
        "id",
        "event_id",
        "event_type",
        "status",
        "attempts",
        "last_error_code",
        "last_status_code",
        "created_at",
        "delivered_at",
    }
    serialized = json.dumps(body)
    for marker in (_SECRET_A, _ENDPOINT_A, _PAYLOAD_MARKER, "payload_hash"):
        assert marker not in serialized
    assert str(pending.id) not in serialized


def test_no_secret_payload_or_stack_trace_in_logs_or_database(
    client: TestClient, db: DBSession, seeded: _Seed, caplog: pytest.LogCaptureFixture
) -> None:
    endpoint = f"{_ENDPOINT_A}?token={_QUERY_SECRET}"
    integration = _create_integration(client, seeded, endpoint=endpoint)
    with caplog.at_level(logging.INFO, logger="talentos"):
        delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
        integrations_service.deliver_webhook(
            db, delivery.id, sender=StubWebhookSender([WebhookDeliveryResult(500, None)])
        )
        db.commit()

    refreshed = _refresh(db, delivery)
    assert refreshed.endpoint_snapshot == _ENDPOINT_A
    assert _QUERY_SECRET not in _db_text(db)
    assert _PAYLOAD_MARKER not in _db_text(db)
    for marker in (
        _SECRET_A,
        _QUERY_SECRET,
        _PAYLOAD_MARKER,
        _CV_MARKER,
        "Traceback",
    ):
        assert marker not in caplog.text


def test_httpx_adapter_uses_mock_transport_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    original_client = httpx.Client

    def client(**kwargs: object) -> httpx.Client:
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    result = HttpxWebhookSender().send(
        "https://hooks.example.test/sink", {"X-Test": "synthetic"}, b"{}"
    )

    assert result == WebhookDeliveryResult(200, None)
    assert len(seen) == 1
    assert seen[0].headers["X-Test"] == "synthetic"


def test_httpx_adapter_maps_timeout_to_stable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("synthetic timeout")

    original_client = httpx.Client

    def client(**kwargs: object) -> httpx.Client:
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    result = HttpxWebhookSender().send("https://hooks.example.test/sink", {}, b"{}")

    assert result == WebhookDeliveryResult(None, "provider_timeout")


def test_task_rejects_foreign_context_without_sending(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    task_sessions: None,
    stub_sender: StubWebhookSender,
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()

    with caplog.at_level(logging.WARNING, logger="talentos"):
        webhook_tasks.deliver_webhook(
            str(delivery.id), seeded.org_b, str(delivery.correlation_id)
        )
        webhook_tasks.deliver_webhook(str(delivery.id), seeded.org_a, str(uuid.uuid4()))

    assert "organization_mismatch" in caplog.text
    assert "correlation_mismatch" in caplog.text
    assert stub_sender.calls == []
    assert _refresh(db, delivery).status is WebhookDeliveryStatus.PENDING


def test_task_retries_transient_failure_with_bounded_countdown(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    task_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    db.commit()
    sender = StubWebhookSender([WebhookDeliveryResult(503, "provider_rejected")])
    monkeypatch.setattr(integrations_service, "HttpxWebhookSender", lambda: sender)
    retries: list[int] = []

    def retry(*, exc: object, countdown: int) -> NoReturn:
        assert exc is not None
        retries.append(countdown)
        raise _RetryCaptured(countdown)

    monkeypatch.setattr(webhook_tasks.deliver_webhook, "retry", retry)
    with pytest.raises(_RetryCaptured) as captured:
        webhook_tasks.deliver_webhook(
            str(delivery.id), seeded.org_a, str(delivery.correlation_id)
        )

    assert captured.value.countdown == 2
    assert retries == [2]
    refreshed = _refresh(db, delivery)
    assert refreshed.status is WebhookDeliveryStatus.FAILED
    assert refreshed.attempts == 1


def test_task_does_not_retry_dead_letter(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    task_sessions: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration = _create_integration(client, seeded)
    delivery = _create_delivery(db, seeded, uuid.UUID(str(integration["id"])))
    delivery.status = WebhookDeliveryStatus.DEAD_LETTER
    delivery.attempts = 3
    db.commit()
    calls: list[object] = []

    def unexpected(*_args: object, **_kwargs: object) -> NoReturn:
        calls.append("called")
        raise AssertionError("dead-letter no debe reintentarse")

    monkeypatch.setattr(integrations_service, "deliver_webhook", unexpected)
    monkeypatch.setattr(webhook_tasks.deliver_webhook, "retry", unexpected)

    webhook_tasks.deliver_webhook(
        str(delivery.id), seeded.org_a, str(delivery.correlation_id)
    )

    assert calls == []
    refreshed = _refresh(db, delivery)
    assert refreshed.status is WebhookDeliveryStatus.DEAD_LETTER
    assert refreshed.attempts == 3


def test_deliveries_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-deliveries.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.db.base.Base", Base, raising=True)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0014_webhook_events")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert "webhook_deliveries" not in before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert "webhook_deliveries" in after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0014_webhook_events")
        reverted = set(inspect(engine).get_table_names())
        assert "webhook_deliveries" not in reverted
    finally:
        engine.dispose()
