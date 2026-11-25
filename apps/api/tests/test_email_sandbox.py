"""Tests de correo sandbox: aprobación separada, tenant y sin PII.

SQLite aislada, usuarios sintéticos, clave Fernet efímera y sender stub.
Sin SMTP, red, CV real, secreto real ni decisión automática de contratación.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import email_validator
import pytest
from alembic import command
from alembic.config import Config
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
from app.identity.models import User
from app.integrations import service as integrations_service
from app.integrations.email import (
    EmailDeliveryResult,
    EmailMessage,
    SandboxEmailSender,
    StubEmailSender,
)
from app.integrations.models import (
    EmailApprovalStatus,
    EmailDeliveryStatus,
    EmailDraft,
)
from app.integrations.schemas import EmailDraftDetail
from app.integrations.service import _email_body_hash, _render_email_text
from app.main import app

_URL = "/api/v1/integrations"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-email-sandbox@example.test"
_OWNER_B = "owner-b-email-sandbox@example.test"
_APPROVER = "approver-email-sandbox@example.test"
_VIEWER = "viewer-email-sandbox@example.test"

_CANDIDATE_A = uuid.UUID("8a7d6c5b-4a39-4e28-9b17-0c6d5e4f3a21")
_CANDIDATE_B = uuid.UUID("1f2e3d4c-5b6a-4978-8899-aabbccddeeff")
_TOPIC = "Entrevista tecnica"
_CTA = "Confirmar disponibilidad"
_ENDPOINT = "https://hooks.email-sandbox.example.test/sink"
_SECRET = "SyntheticEmailSandboxSecretDoNotExpose123"
_EMAIL_MARKER = "candidate-email-sandbox@example.test"
_CV_MARKER = "SyntheticCvSandboxMarker"
_SECRET_MARKER = "SyntheticTokenSandboxMarkerDoNotExpose"
_NOT_FOUND = "Recurso de integración no encontrado."
_UNAVAILABLE = "Configuración de integración no disponible."


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
def seeded(client: TestClient) -> _Seed:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Owner B"),
        (_APPROVER, "Synthetic Approver"),
        (_VIEWER, "Synthetic Viewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Email Sandbox Org A", "email-sandbox-org-a")
    _invite(client, org_a, _APPROVER, "admin")
    _invite(client, org_a, _VIEWER, "viewer")

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Email Sandbox Org B", "email-sandbox-org-b")
    # Owner A pertenece a B para que el filtro tenant sea la única diferencia.
    _invite(client, org_b, _OWNER_A, "admin")

    _login(client, _OWNER_A)
    return _Seed(org_a=org_a, org_b=org_b)


def _register(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD, "name": name}
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


def _invite(client: TestClient, org_id: str, email: str, role: str) -> None:
    response = client.post(
        f"{_ORGS_URL}/{org_id}/members",
        json={"email": email, "role": role},
        headers=_headers(org_id),
    )
    assert response.status_code == 201, response.text


def _headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


def _user_id(db: DBSession, email: str) -> uuid.UUID:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user.id


def _create_integration(
    client: TestClient,
    seed: _Seed,
    *,
    provider: str = "email_sandbox",
    config: dict[str, object] | None = None,
    org_id: str | None = None,
) -> str:
    payload = config if config is not None else {"sink": "local_log"}
    response = client.post(
        _URL,
        json={"provider": provider, "config": payload},
        headers=_headers(org_id or seed.org_a),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _draft_body(
    *,
    candidate_id: uuid.UUID = _CANDIDATE_A,
    topic: str = _TOPIC,
    call_to_action: str = _CTA,
    template: str = "initial_contact",
    language: str = "es",
    **extra: object,
) -> dict[str, object]:
    body: dict[str, object] = {
        "candidate_id": str(candidate_id),
        "template": template,
        "topic": topic,
        "language": language,
        "call_to_action": call_to_action,
    }
    body.update(extra)
    return body


def _create_draft(
    client: TestClient,
    seed: _Seed,
    integration_id: str,
    *,
    body: dict[str, object] | None = None,
    org_id: str | None = None,
    expected: int = 201,
) -> dict[str, object]:
    response = client.post(
        f"{_URL}/{integration_id}/email-drafts",
        json=body if body is not None else _draft_body(),
        headers=_headers(org_id or seed.org_a),
    )
    assert response.status_code == expected, response.text
    result: dict[str, object] = response.json()
    return result


def _post_action(
    client: TestClient,
    seed: _Seed,
    integration_id: str,
    draft_id: str,
    action: str,
    *,
    org_id: str | None = None,
    expected: int = 200,
) -> dict[str, object]:
    response = client.post(
        f"{_URL}/{integration_id}/email-drafts/{draft_id}/{action}",
        headers=_headers(org_id or seed.org_a),
    )
    assert response.status_code == expected, response.text
    result: dict[str, object] = response.json() if expected == 200 else {}
    return result


def _stub_sender(
    monkeypatch: pytest.MonkeyPatch, *results: EmailDeliveryResult
) -> StubEmailSender:
    sender = StubEmailSender(results)
    monkeypatch.setattr(integrations_service, "SandboxEmailSender", lambda: sender)
    return sender


def _row(db: DBSession, draft_id: str) -> EmailDraft:
    db.expire_all()
    row = db.get(EmailDraft, uuid.UUID(str(draft_id)))
    assert row is not None
    db.refresh(row)
    return row


def _audit_count(db: DBSession, action: str) -> int:
    value = db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
    )
    return int(value or 0)


def _raw_row(db: DBSession, draft_id: str) -> str:
    """Serializa todas las columnas mapeadas sin SQL crudo ni bind de UUID."""
    row = _row(db, draft_id)
    return " ".join(
        str(getattr(row, attr.key)) for attr in inspect(type(row)).mapper.column_attrs
    )


def _assert_error(response: object, status_code: int, message: str) -> None:
    """El handler global envuelve los errores en `error.message`."""
    assert response.status_code == status_code  # type: ignore[attr-defined]
    payload = response.json()  # type: ignore[attr-defined]
    assert payload["error"]["message"] == message


def test_create_persists_only_hash_and_sanitized_metadata(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration_id = _create_integration(client, seeded)
    with caplog.at_level(logging.INFO, logger="talentos"):
        created = _create_draft(client, seeded, integration_id)

    assert set(created) == set(EmailDraftDetail.model_fields)
    assert created["approval_status"] == EmailApprovalStatus.PENDING.value
    assert created["delivery_status"] == EmailDeliveryStatus.NOT_SENT.value
    assert created["attempts"] == 0
    assert str(created["requested_by"]) == str(_user_id(db, _OWNER_A))
    assert created["decided_by"] is None
    assert created["decided_at"] is None

    row = _row(db, str(created["id"]))
    expected_text = _render_email_text(
        template=row.template,
        topic=row.topic,
        language=row.language,
        call_to_action=row.call_to_action,
    )
    assert row.body_hash == _email_body_hash(expected_text)
    assert len(row.body_hash) == 64
    assert not hasattr(row, "body")
    assert not hasattr(row, "recipient")
    assert not hasattr(row, "email")
    assert _audit_count(db, "email.draft_created") == 1
    assert _EMAIL_MARKER not in _raw_row(db, str(created["id"]))
    assert _EMAIL_MARKER not in caplog.text


def test_send_before_approval_is_rejected_and_sender_not_invoked(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _stub_sender(monkeypatch)
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)

    response = client.post(
        f"{_URL}/{integration_id}/email-drafts/{draft['id']}/send",
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 409, response.text
    assert stub.messages == []

    row = _row(db, str(draft["id"]))
    assert row.approval_status is EmailApprovalStatus.PENDING
    assert row.delivery_status is EmailDeliveryStatus.NOT_SENT
    assert row.attempts == 0
    assert _audit_count(db, "email.sent") == 0
    assert _audit_count(db, "email.send_failed") == 0


def test_approval_is_separate_from_send(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _stub_sender(monkeypatch)
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)

    _login(client, _APPROVER)
    approved = _post_action(
        client, seeded, integration_id, str(draft["id"]), "approve"
    )
    assert approved["approval_status"] == EmailApprovalStatus.APPROVED.value
    assert approved["delivery_status"] == EmailDeliveryStatus.NOT_SENT.value
    assert approved["decided_at"] is not None
    assert str(approved["decided_by"]) == str(_user_id(db, _APPROVER))
    assert stub.messages == []

    row = _row(db, str(draft["id"]))
    assert row.approval_status is EmailApprovalStatus.APPROVED
    assert row.delivery_status is EmailDeliveryStatus.NOT_SENT
    assert row.attempts == 0
    assert _audit_count(db, "email.approved") == 1
    assert _audit_count(db, "email.sent") == 0


def test_reject_is_terminal_and_blocks_send(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _stub_sender(monkeypatch)
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)

    _login(client, _APPROVER)
    rejected = _post_action(
        client, seeded, integration_id, str(draft["id"]), "reject"
    )
    assert rejected["approval_status"] == EmailApprovalStatus.REJECTED.value
    assert _audit_count(db, "email.rejected") == 1

    response = client.post(
        f"{_URL}/{integration_id}/email-drafts/{draft['id']}/send",
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 409, response.text
    assert stub.messages == []
    row = _row(db, str(draft["id"]))
    assert row.approval_status is EmailApprovalStatus.REJECTED
    assert row.delivery_status is EmailDeliveryStatus.NOT_SENT
    assert row.attempts == 0


def test_self_approval_forbidden_and_distinct_admin_allowed(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
) -> None:
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)

    self_response = client.post(
        f"{_URL}/{integration_id}/email-drafts/{draft['id']}/approve",
        headers=_headers(seeded.org_a),
    )
    assert self_response.status_code == 403, self_response.text
    assert _row(db, str(draft["id"])).approval_status is EmailApprovalStatus.PENDING

    _login(client, _APPROVER)
    approved = _post_action(
        client, seeded, integration_id, str(draft["id"]), "approve"
    )
    assert approved["approval_status"] == EmailApprovalStatus.APPROVED.value
    assert str(approved["decided_by"]) == str(_user_id(db, _APPROVER))


def test_viewer_reads_but_cannot_create_decide_or_send(
    client: TestClient, seeded: _Seed
) -> None:
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)

    _login(client, _VIEWER)
    listing = client.get(
        f"{_URL}/{integration_id}/email-drafts", headers=_headers(seeded.org_a)
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1

    detail = client.get(
        f"{_URL}/{integration_id}/email-drafts/{draft['id']}",
        headers=_headers(seeded.org_a),
    )
    assert detail.status_code == 200, detail.text

    create_response = client.post(
        f"{_URL}/{integration_id}/email-drafts",
        json=_draft_body(candidate_id=_CANDIDATE_B),
        headers=_headers(seeded.org_a),
    )
    assert create_response.status_code == 403, create_response.text
    for action in ("approve", "reject", "send"):
        response = client.post(
            f"{_URL}/{integration_id}/email-drafts/{draft['id']}/{action}",
            headers=_headers(seeded.org_a),
        )
        assert response.status_code == 403, response.text


def test_cross_tenant_routes_do_not_reveal_drafts(
    client: TestClient,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _stub_sender(monkeypatch)
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)
    base = f"{_URL}/{integration_id}/email-drafts"
    headers_b = _headers(seeded.org_b)

    create_response = client.post(
        base, json=_draft_body(candidate_id=_CANDIDATE_B), headers=headers_b
    )
    _assert_error(create_response, 404, _NOT_FOUND)

    list_response = client.get(base, headers=headers_b)
    _assert_error(list_response, 404, _NOT_FOUND)
    detail_response = client.get(f"{base}/{draft['id']}", headers=headers_b)
    _assert_error(detail_response, 404, _NOT_FOUND)

    for action in ("approve", "reject", "send"):
        response = client.post(f"{base}/{draft['id']}/{action}", headers=headers_b)
        _assert_error(response, 404, _NOT_FOUND)
    assert stub.messages == []

    _login(client, _OWNER_B)
    outsider = client.get(base, headers=_headers(seeded.org_a))
    assert outsider.status_code == 403, outsider.text


def test_unique_natural_key_is_idempotent(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    integration_id = _create_integration(client, seeded)
    body = _draft_body()
    first = _create_draft(client, seeded, integration_id, body=body, expected=201)
    second = _create_draft(client, seeded, integration_id, body=body, expected=200)
    assert second["id"] == first["id"]
    assert second["body_hash"] == first["body_hash"]

    count = db.scalar(
        select(func.count())
        .select_from(EmailDraft)
        .where(EmailDraft.organization_id == uuid.UUID(seeded.org_a))
    )
    assert count == 1
    assert _audit_count(db, "email.draft_created") == 1


def test_sandbox_sender_is_deterministic_and_logs_no_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    subject = "SyntheticSandboxSubjectDoNotLog"
    body = "SyntheticSandboxBodyDoNotLog"
    message = EmailMessage(_CANDIDATE_A, subject, body)
    sender = SandboxEmailSender()

    with caplog.at_level(logging.INFO, logger="talentos"):
        first = sender.send(message)
        second = sender.send(message)

    assert first == second
    assert first.succeeded
    assert first.error_code is None
    assert first.ref is not None and first.ref.startswith("sandbox:")
    assert first.ref in caplog.text
    assert subject not in caplog.text
    assert body not in caplog.text


def test_sender_failure_persists_error_code_without_text(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = _stub_sender(
        monkeypatch, EmailDeliveryResult(None, "provider_rejected")
    )
    integration_id = _create_integration(client, seeded)
    draft = _create_draft(client, seeded, integration_id)

    _login(client, _APPROVER)
    _post_action(client, seeded, integration_id, str(draft["id"]), "approve")
    _login(client, _OWNER_A)
    with caplog.at_level(logging.INFO, logger="talentos"):
        sent = _post_action(client, seeded, integration_id, str(draft["id"]), "send")

    assert sent["delivery_status"] == EmailDeliveryStatus.FAILED.value
    assert sent["last_error_code"] == "provider_rejected"
    assert sent["attempts"] == 1
    row = _row(db, str(draft["id"]))
    assert row.delivery_status is EmailDeliveryStatus.FAILED
    assert row.last_error_code == "provider_rejected"
    assert row.sent_at is None
    assert len(stub.messages) == 1
    assert _audit_count(db, "email.send_failed") == 1
    assert _audit_count(db, "email.sent") == 0
    assert "provider_rejected" in caplog.text
    assert stub.messages[0].subject not in caplog.text
    assert stub.messages[0].text not in caplog.text


def test_rejects_unknown_inactive_and_wrong_provider(
    client: TestClient, seeded: _Seed
) -> None:
    missing = str(uuid.uuid4())
    missing_response = client.post(
        f"{_URL}/{missing}/email-drafts",
        json=_draft_body(),
        headers=_headers(seeded.org_a),
    )
    _assert_error(missing_response, 404, _NOT_FOUND)

    webhook_id = _create_integration(
        client,
        seeded,
        provider="webhook_outbound",
        config={"endpoint": _ENDPOINT, "secret": _SECRET},
    )
    wrong_response = client.post(
        f"{_URL}/{webhook_id}/email-drafts",
        json=_draft_body(),
        headers=_headers(seeded.org_a),
    )
    _assert_error(wrong_response, 404, _NOT_FOUND)

    email_id = _create_integration(client, seeded)
    patched = client.patch(
        f"{_URL}/{email_id}",
        json={"status": "disabled", "expected_version": 1},
        headers=_headers(seeded.org_a),
    )
    assert patched.status_code == 200, patched.text
    inactive_response = client.post(
        f"{_URL}/{email_id}/email-drafts",
        json=_draft_body(),
        headers=_headers(seeded.org_a),
    )
    _assert_error(inactive_response, 503, _UNAVAILABLE)
    listing = client.get(
        f"{_URL}/{email_id}/email-drafts", headers=_headers(seeded.org_a)
    )
    _assert_error(listing, 503, _UNAVAILABLE)


def test_contract_rejects_direct_pii_and_keeps_responses_clean(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    caplog: pytest.LogCaptureFixture,
) -> None:
    integration_id = _create_integration(client, seeded)
    forbidden_keys: Sequence[tuple[str, str]] = (
        ("email", _EMAIL_MARKER),
        ("name", "SyntheticDirectName"),
        ("cv", _CV_MARKER),
        ("secret", _SECRET_MARKER),
        ("token", "SyntheticDirectToken"),
        ("body", "SyntheticDirectBody"),
        ("recipient", _EMAIL_MARKER),
    )
    with caplog.at_level(logging.INFO, logger="talentos"):
        for key, value in forbidden_keys:
            response = client.post(
                f"{_URL}/{integration_id}/email-drafts",
                json=_draft_body(**{key: value}),
                headers=_headers(seeded.org_a),
            )
            assert response.status_code == 422, (key, response.text)
        for text in (_EMAIL_MARKER, f"cv {_CV_MARKER}", f"token {_SECRET_MARKER}"):
            for field in ("topic", "call_to_action"):
                response = client.post(
                    f"{_URL}/{integration_id}/email-drafts",
                    json=_draft_body(**{field: text}),
                    headers=_headers(seeded.org_a),
                )
                assert response.status_code == 422, (field, response.text)

        created = _create_draft(client, seeded, integration_id)

    for marker in (_EMAIL_MARKER, _CV_MARKER, _SECRET_MARKER):
        assert marker not in str(created)
        assert marker not in _raw_row(db, str(created["id"]))
        assert marker not in caplog.text
    audit_dump = " ".join(str(item.action) for item in db.scalars(select(AuditLog)).all())
    for marker in (_EMAIL_MARKER, _CV_MARKER, _SECRET_MARKER):
        assert marker not in audit_dump


def test_email_drafts_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-email-drafts.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.db.base.Base", Base, raising=True)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0015_webhook_deliveries")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert "email_drafts" not in before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert "email_drafts" in after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0015_webhook_deliveries")
        reverted = set(inspect(engine).get_table_names())
        assert "email_drafts" not in reverted
    finally:
        engine.dispose()
