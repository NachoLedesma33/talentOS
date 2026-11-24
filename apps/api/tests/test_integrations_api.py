"""Tests de integración del núcleo de integraciones.

SQLite aislada, cookies y headers reales, clave Fernet sintética generada en
cada test y datos de prueba ficticios. Sin red, secretos reales ni webhooks.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import email_validator
import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
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
from app.integrations.crypto import current_key_id, decrypt_config
from app.integrations.models import Integration, IntegrationKeyMissingError
from app.main import app

_URL = "/api/v1/integrations"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-integrations-api@example.test"
_OWNER_B = "owner-b-integrations-api@example.test"
_VIEWER = "viewer-integrations-api@example.test"
_SECRET_A = "SyntheticSecretMarkerDoNotExpose123"
_SECRET_B = "SyntheticRotatedSecretDoNotExpose456"
_ENDPOINT_A = "https://hooks.integrations.example.test/sink"

_PUBLIC_KEYS = {
    "id",
    "provider",
    "status",
    "config_version",
    "key_id",
    "created_at",
    "updated_at",
}


@dataclass(frozen=True)
class _Seed:
    org_a: str
    org_b: str


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture(autouse=True)
def _integration_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clave Fernet efímera por test; nunca se comparte con otros entornos."""
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
        (_VIEWER, "Synthetic Viewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Integrations Org A", "integrations-org-a")
    response = client.post(
        f"{_ORGS_URL}/{org_a}/members",
        json={"email": _VIEWER, "role": "viewer"},
        headers=_headers(org_a),
    )
    assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Integrations Org B", "integrations-org-b")

    _login(client, _OWNER_A)
    return _Seed(org_a=org_a, org_b=org_b)


def _create(
    client: TestClient,
    seed: _Seed,
    body: dict[str, object],
    *,
    org_id: str | None = None,
) -> dict[str, object]:
    response = client.post(
        _URL, json=body, headers=_headers(org_id or seed.org_a)
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


def _webhook_body(secret: str = _SECRET_A) -> dict[str, object]:
    return {
        "provider": "webhook_outbound",
        "config": {"endpoint": _ENDPOINT_A, "secret": secret},
    }


def _get_stored_token(db: DBSession, integration_id: str) -> str:
    token = db.scalar(
        select(Integration.encrypted_config_ref).where(
            Integration.id == uuid.UUID(integration_id)
        )
    )
    assert isinstance(token, str)
    return token


def test_post_webhook_outbound_persists_only_encrypted_config(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="talentos"):
        created = _create(client, seeded, _webhook_body())

    assert set(created) == _PUBLIC_KEYS
    token = _get_stored_token(db, str(created["id"]))
    assert token.startswith("gAAAAA")
    assert _SECRET_A not in token
    assert _ENDPOINT_A not in token
    assert decrypt_config(token) == {"endpoint": _ENDPOINT_A, "secret": _SECRET_A}
    stored_key_id = db.scalar(
        select(Integration.key_id).where(Integration.id == uuid.UUID(str(created["id"])))
    )
    assert stored_key_id == current_key_id() == created["key_id"]
    assert _SECRET_A not in caplog.text
    assert _ENDPOINT_A not in caplog.text
    assert "gAAAAA" not in caplog.text


def test_get_list_and_detail_never_return_config_or_token(
    client: TestClient, seeded: _Seed
) -> None:
    created = _create(client, seeded, _webhook_body())

    listed = client.get(_URL, headers=_headers(seeded.org_a))
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["total"] == 1
    assert set(payload) == {"items", "total", "limit", "offset"}
    assert all(set(item) == _PUBLIC_KEYS for item in payload["items"])

    detail = client.get(
        f"{_URL}/{created['id']}", headers=_headers(seeded.org_a)
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert set(body) == _PUBLIC_KEYS
    serialized = json.dumps({"list": payload, "detail": body})
    for forbidden in (_SECRET_A, _ENDPOINT_A, "encrypted_config_ref"):
        assert forbidden not in serialized
    for item in [*payload["items"], body]:
        assert not {"config", "secret", "token"} & set(item)


def test_cross_tenant_reads_and_writes_do_not_reveal_existence(
    client: TestClient, seeded: _Seed
) -> None:
    created = _create(client, seeded, _webhook_body())

    _login(client, _OWNER_B)
    detail = client.get(
        f"{_URL}/{created['id']}", headers=_headers(seeded.org_b)
    )
    assert detail.status_code == 404, detail.text
    patched = client.patch(
        f"{_URL}/{created['id']}",
        json={"status": "disabled", "expected_version": 1},
        headers=_headers(seeded.org_b),
    )
    assert patched.status_code == 404, patched.text

    # Mismo proveedor en otra organización: éxito, sin filtrar la fila ajena.
    other = _create(client, seeded, _webhook_body(), org_id=seeded.org_b)
    assert other["id"] != created["id"]

    duplicate = client.post(
        _URL, json=_webhook_body(), headers=_headers(seeded.org_b)
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "conflict"


def test_viewer_reads_but_cannot_write(client: TestClient, seeded: _Seed) -> None:
    created = _create(client, seeded, _webhook_body())

    _login(client, _VIEWER)
    listed = client.get(_URL, headers=_headers(seeded.org_a))
    assert listed.status_code == 200, listed.text
    detail = client.get(f"{_URL}/{created['id']}", headers=_headers(seeded.org_a))
    assert detail.status_code == 200, detail.text
    assert set(detail.json()) == _PUBLIC_KEYS

    rejected_post = client.post(
        _URL, json=_webhook_body(), headers=_headers(seeded.org_a)
    )
    assert rejected_post.status_code == 403, rejected_post.text
    rejected_patch = client.patch(
        f"{_URL}/{created['id']}",
        json={"status": "disabled", "expected_version": 1},
        headers=_headers(seeded.org_a),
    )
    assert rejected_patch.status_code == 403, rejected_patch.text


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "unknown", "config": {"sink": "local_log"}},
        {"provider": "email_sandbox", "config": {"sink": "remote"}},
        {"provider": "email_sandbox", "config": {"sink": "local_log", "secret": _SECRET_A}},
        {"provider": "webhook_outbound", "config": {"endpoint": _ENDPOINT_A, "secret": "short"}},
        {"provider": "webhook_outbound", "config": {"secret": _SECRET_A}},
        {
            "provider": "webhook_inbound",
            "config": {"secret": _SECRET_A, "tolerance_seconds": 10},
        },
    ],
)
def test_invalid_provider_or_config_returns_422(
    client: TestClient, seeded: _Seed, body: dict[str, object]
) -> None:
    response = client.post(_URL, json=body, headers=_headers(seeded.org_a))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_encryption_key_fails_deterministically_without_writing(
    client: TestClient,
    db: DBSession,
    seeded: _Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(IntegrationKeyMissingError) as exc:
        current_key_id()
    assert exc.value.code == "integration_key_missing"

    response = client.post(_URL, json=_webhook_body(), headers=_headers(seeded.org_a))
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "service_unavailable"
    assert db.scalar(select(func.count()).select_from(Integration)) == 0


def test_optimistic_version_and_config_rotation(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    created = _create(client, seeded, _webhook_body())
    integration_id = str(created["id"])
    assert created["config_version"] == 1

    rotated = client.patch(
        f"{_URL}/{integration_id}",
        json={
            "config": {"endpoint": _ENDPOINT_A, "secret": _SECRET_B},
            "expected_version": 1,
        },
        headers=_headers(seeded.org_a),
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["config_version"] == 2
    assert decrypt_config(_get_stored_token(db, integration_id)) == {
        "endpoint": _ENDPOINT_A,
        "secret": _SECRET_B,
    }
    assert _SECRET_A not in _get_stored_token(db, integration_id)

    stale = client.patch(
        f"{_URL}/{integration_id}",
        json={"status": "disabled", "expected_version": 1},
        headers=_headers(seeded.org_a),
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "conflict"
    assert current_key_id() == rotated.json()["key_id"]

    disabled = client.patch(
        f"{_URL}/{integration_id}",
        json={"status": "disabled", "expected_version": 2},
        headers=_headers(seeded.org_a),
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["config_version"] == 2

    filtered = client.get(
        _URL, params={"status": "disabled"}, headers=_headers(seeded.org_a)
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()["items"]] == [integration_id]


def test_email_sandbox_needs_no_real_secret(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    created = _create(
        client, seeded, {"provider": "email_sandbox", "config": {"sink": "local_log"}}
    )
    assert created["provider"] == "email_sandbox"
    assert decrypt_config(_get_stored_token(db, str(created["id"]))) == {
        "sink": "local_log"
    }


def test_audit_records_have_no_sensitive_payload(
    client: TestClient, db: DBSession, seeded: _Seed
) -> None:
    created = _create(client, seeded, _webhook_body())
    integration_id = str(created["id"])
    response = client.patch(
        f"{_URL}/{integration_id}",
        json={"status": "disabled", "expected_version": 1},
        headers=_headers(seeded.org_a),
    )
    assert response.status_code == 200, response.text

    actions = {
        str(row.action)
        for row in db.scalars(
            select(AuditLog).where(AuditLog.resource_id == uuid.UUID(integration_id))
        ).all()
    }
    assert actions == {"integration.created", "integration.updated"}
    rows = db.execute(
        text(
            "SELECT action, resource_type, actor_id, resource_id, organization_id "
            "FROM audit_log"
        )
    ).all()
    assert _SECRET_A not in json.dumps([tuple(row) for row in rows], default=str)
    assert _ENDPOINT_A not in json.dumps([tuple(row) for row in rows], default=str)


def test_integrations_migration_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migration-integrations.db"
    url = f"sqlite:///{db_file}"

    class _Settings:
        DATABASE_URL = url

    monkeypatch.setattr("app.core.config.get_settings", lambda: _Settings())
    monkeypatch.setattr("logging.config.fileConfig", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.db.base.Base", Base, raising=True)
    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))

    command.upgrade(alembic_config, "0012_automation")
    engine = create_engine(url)
    try:
        before = set(inspect(engine).get_table_names())
        assert "integrations" not in before

        command.upgrade(alembic_config, "head")
        after = set(inspect(engine).get_table_names())
        assert "integrations" in after
        command.check(alembic_config)

        command.downgrade(alembic_config, "0012_automation")
        reverted = set(inspect(engine).get_table_names())
        assert "integrations" not in reverted
    finally:
        engine.dispose()
