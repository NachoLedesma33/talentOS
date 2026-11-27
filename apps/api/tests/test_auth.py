from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.identity.models  # noqa: F401  # registra las tablas antes de create_all
from app.core.config import get_settings
from app.db import base as base_module
from app.db.base import Base
from app.db.session import get_db
from app.identity.models import (
    Invitation,
    Membership,
    MembershipRole,
    Organization,
    PasswordResetToken,
    User,
)
from app.identity.models import Session as UserSession
from app.identity.schemas import MemberRoleUpdate, OrganizationCreate
from app.identity.security import hash_token
from app.main import app

_EMAIL = "synthetic.user@example.com"
_PASSWORD = "SyntheticPass123"
_NAME = "Synthetic User"
_COOKIE = get_settings().SESSION_COOKIE_NAME


@pytest.fixture(scope="module", autouse=True)
def _isolate_unit1_metadata() -> Iterator[None]:
    # Importar el router de auth registra las tablas identity en Base.metadata.
    # Al cerrar este módulo se publica una Base limpia para el test de Fase 1
    # que comprueba que su metadata solo contiene la tabla probe.
    yield
    importlib.reload(base_module)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _register(client: TestClient, email: str = _EMAIL) -> Response:
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "name": _NAME},
    )


def _login(client: TestClient, password: str = _PASSWORD) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": password},
    )


def test_register_creates_active_user_without_auto_login(
    client: TestClient, db: DBSession
) -> None:
    response = _register(client, "SYNTHETIC.USER@EXAMPLE.COM")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == _EMAIL
    assert body["name"] == _NAME
    assert body["status"] == "active"
    assert "password" not in body
    assert _COOKIE not in response.cookies
    assert len(db.scalars(select(User)).all()) == 1


def test_duplicate_email_returns_409_without_second_user(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201

    response = _register(client, _EMAIL.upper())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert len(db.scalars(select(User)).all()) == 1


def test_password_hash_never_contains_plain_password(client: TestClient, db: DBSession) -> None:
    assert _register(client).status_code == 201

    stored = db.scalar(select(User.password_hash).where(User.email == _EMAIL))
    assert stored is not None
    assert stored != _PASSWORD
    assert _PASSWORD not in stored


def test_login_sets_httponly_lax_cookie_and_stores_only_token_hash(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201

    response = _login(client)

    assert response.status_code == 200
    assert response.json()["email"] == _EMAIL
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert f"{_COOKIE}=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "max-age=86400" in set_cookie
    assert "secure" not in set_cookie

    plain_token = client.cookies.get(_COOKIE)
    assert plain_token
    stored_hash = db.scalar(select(UserSession.token_hash))
    assert stored_hash is not None
    assert stored_hash != plain_token
    assert plain_token not in stored_hash


def test_wrong_password_returns_401_without_cookie(client: TestClient, db: DBSession) -> None:
    assert _register(client).status_code == 201

    response = _login(client, "WrongSyntheticPass")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert _COOKIE not in client.cookies
    assert db.scalars(select(UserSession)).all() == []


def test_me_without_cookie_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_with_valid_cookie_returns_user_and_empty_organizations(client: TestClient) -> None:
    registered = _register(client)
    assert registered.status_code == 201
    assert _login(client).status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == registered.json()["id"]
    assert body["email"] == _EMAIL
    assert body["name"] == _NAME
    assert body["status"] == "active"
    assert body["organizations"] == []
    assert body["onboarding"] == {"step": "create_organization"}


def test_me_reports_complete_step_for_user_with_organization(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201
    user = db.scalar(select(User))
    assert user is not None
    organization = Organization(name="Synthetic Org", slug="synthetic-org")
    db.add(organization)
    db.flush()
    db.add(
        Membership(
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.OWNER,
        )
    )
    db.commit()
    assert _login(client).status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["onboarding"] == {"step": "complete"}


def test_me_reports_accept_invitation_step_for_pending_invitation(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201
    user = db.scalar(select(User))
    assert user is not None
    organization = Organization(name="Inviting Org", slug="inviting-org")
    db.add(organization)
    db.flush()
    db.add(
        Invitation(
            organization_id=organization.id,
            email=_EMAIL,
            role=MembershipRole.VIEWER,
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()
    assert _login(client).status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["onboarding"] == {"step": "accept_invitation"}


def test_me_ignores_expired_and_accepted_invitations(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201
    user = db.scalar(select(User))
    assert user is not None
    organization = Organization(name="Closed Org", slug="closed-org")
    db.add(organization)
    db.flush()
    db.add(
        Invitation(
            organization_id=organization.id,
            email=_EMAIL,
            role=MembershipRole.VIEWER,
            token_hash="b" * 64,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            accepted_at=datetime.now(UTC),
        )
    )
    db.commit()
    assert _login(client).status_code == 200

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["onboarding"] == {"step": "create_organization"}


def test_expired_session_is_rejected(client: TestClient, db: DBSession) -> None:
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200
    session = db.scalar(select(UserSession))
    assert session is not None
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_logout_revokes_session(client: TestClient, db: DBSession) -> None:
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"message": "Sesión cerrada."}
    assert _COOKIE not in client.cookies
    assert client.get("/api/v1/auth/me").status_code == 401
    session = db.scalar(select(UserSession))
    assert session is not None
    assert session.revoked_at is not None


def test_logout_with_foreign_origin_is_forbidden(client: TestClient, db: DBSession) -> None:
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200

    response = client.post(
        "/api/v1/auth/logout", headers={"Origin": "https://foreign.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert client.get("/api/v1/auth/me").status_code == 200
    session = db.scalar(select(UserSession))
    assert session is not None
    assert session.revoked_at is None


def test_logout_with_configured_origin_is_allowed(client: TestClient) -> None:
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200

    response = client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}
    )

    assert response.status_code == 200
    assert _COOKIE not in client.cookies


def _forgot(client: TestClient, email: str = _EMAIL) -> Response:
    return client.post("/api/v1/auth/forgot-password", json={"email": email})


def _reset(
    client: TestClient, token: str, password: str = "NewSyntheticPass456"
) -> Response:
    return client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": password}
    )


def test_forgot_password_returns_demo_token_and_stores_only_hash(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201

    response = _forgot(client)

    assert response.status_code == 200
    token = response.json()["dev_token"]
    assert token
    stored = db.scalar(select(PasswordResetToken.token_hash))
    assert stored == hash_token(token)
    assert stored != token


def test_forgot_password_unknown_email_does_not_reveal_account(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201
    known = _forgot(client)

    unknown = _forgot(client, "unknown.synthetic@example.com")

    assert unknown.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]
    assert unknown.json()["dev_token"] is None
    assert len(db.scalars(select(PasswordResetToken)).all()) == 1


def test_reset_password_changes_password_consumes_token_and_revokes_sessions(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201
    assert _login(client).status_code == 200
    token = _forgot(client).json()["dev_token"]

    response = _reset(client, token)

    assert response.status_code == 200
    assert response.json() == {"message": "Contraseña actualizada."}
    assert client.get("/api/v1/auth/me").status_code == 401
    stored = db.scalar(select(PasswordResetToken))
    assert stored is not None
    assert stored.used_at is not None
    assert _login(client).status_code == 401
    assert _login(client, "NewSyntheticPass456").status_code == 200


def test_reset_password_rejects_replayed_expired_and_invalid_tokens(
    client: TestClient, db: DBSession
) -> None:
    assert _register(client).status_code == 201
    token = _forgot(client).json()["dev_token"]
    assert _reset(client, token).status_code == 200

    replay = _reset(client, token)
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "bad_request"

    invalid = _reset(client, "not-a-real-token")
    assert invalid.status_code == 400

    expired_token = _forgot(client).json()["dev_token"]
    active = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.used_at.is_(None))
    )
    assert active is not None
    active.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    expired = _reset(client, expired_token)
    assert expired.status_code == 400


def test_forgot_password_invalidates_previous_tokens(client: TestClient) -> None:
    assert _register(client).status_code == 201
    first = _forgot(client).json()["dev_token"]
    second = _forgot(client).json()["dev_token"]

    assert first != second
    assert _reset(client, first).status_code == 400
    assert _reset(client, second).status_code == 200


def test_reset_password_rejects_short_password(client: TestClient) -> None:
    assert _register(client).status_code == 201
    token = _forgot(client).json()["dev_token"]

    response = _reset(client, token, "short")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/auth/register",
            {
                "email": _EMAIL,
                "password": _PASSWORD,
                "name": _NAME,
                "role": "owner",
            },
        ),
        (
            "/api/v1/auth/login",
            {"email": _EMAIL, "password": _PASSWORD, "is_admin": True},
        ),
        ("/api/v1/auth/forgot-password", {"email": _EMAIL, "user_id": "synthetic"}),
        (
            "/api/v1/auth/reset-password",
            {
                "token": "synthetic-token",
                "password": _PASSWORD,
                "organization_id": "synthetic",
            },
        ),
    ],
)
def test_auth_requests_reject_unknown_fields(
    client: TestClient, path: str, payload: dict[str, object]
) -> None:
    response = client.post(path, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            OrganizationCreate,
            {"name": "Synthetic Org", "slug": "synthetic-org", "is_admin": True},
        ),
        (MemberRoleUpdate, {"role": "owner", "user_id": "synthetic"}),
    ],
)
def test_identity_models_reject_unknown_fields(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_failed_login_logs_security_event_with_correlation(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    assert _register(client).status_code == 201
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="talentos"):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": _EMAIL, "password": "WrongSyntheticPass"},
            headers={"X-Correlation-ID": "corr-synthetic"},
        )

    assert response.status_code == 401
    event = next(record for record in caplog.records if record.getMessage() == "auth_login_failed")
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.correlation_id == "corr-synthetic"
    assert _EMAIL not in caplog.text
    assert "WrongSyntheticPass" not in caplog.text


def test_invalid_reset_logs_security_event_without_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="talentos"):
        response = _reset(client, "not-a-real-token")

    assert response.status_code == 400
    event = next(
        record for record in caplog.records if record.getMessage() == "auth_password_reset_failed"
    )
    assert event.request_id == response.headers["X-Request-ID"]
    assert "not-a-real-token" not in caplog.text


def test_password_reset_events_logged_with_correlation_without_secrets(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    assert _register(client).status_code == 201
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="talentos"):
        forgot = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": _EMAIL},
            headers={"X-Correlation-ID": "corr-recovery"},
        )
        token = forgot.json()["dev_token"]
        reset = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "NewSyntheticPass456"},
            headers={"X-Correlation-ID": "corr-recovery"},
        )

    assert forgot.status_code == 200
    assert reset.status_code == 200
    requested = next(
        record
        for record in caplog.records
        if record.getMessage() == "auth_password_reset_requested"
    )
    succeeded = next(
        record
        for record in caplog.records
        if record.getMessage() == "auth_password_reset_succeeded"
    )
    assert requested.request_id == forgot.headers["X-Request-ID"]
    assert requested.correlation_id == "corr-recovery"
    assert succeeded.request_id == reset.headers["X-Request-ID"]
    assert succeeded.correlation_id == "corr-recovery"
    assert _EMAIL not in caplog.text
    assert token not in caplog.text
    assert "NewSyntheticPass456" not in caplog.text


@pytest.mark.parametrize(
    ("url", "payload"),
    [
        ("/api/v1/auth/register", {"email": _EMAIL, "password": _PASSWORD, "name": _NAME}),
        ("/api/v1/auth/forgot-password", {"email": _EMAIL}),
        ("/api/v1/auth/reset-password", {"token": "synthetic-token", "password": _PASSWORD}),
    ],
)
def test_auth_forms_reject_declined_privacy_consent(
    client: TestClient, url: str, payload: dict[str, str]
) -> None:
    response = client.post(url, json={**payload, "accept_privacy": False})

    assert response.status_code == 422


def test_deployed_environment_requires_explicit_privacy_consent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.identity.schemas.config",
        SimpleNamespace(get_settings=lambda: SimpleNamespace(APP_ENV="production")),
    )
    payload = {"email": _EMAIL, "password": _PASSWORD, "name": _NAME}

    omitted = client.post("/api/v1/auth/register", json=payload)
    accepted = client.post("/api/v1/auth/register", json={**payload, "accept_privacy": True})

    assert omitted.status_code == 422
    assert accepted.status_code == 201


def test_privacy_consent_is_logged_without_pii(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.clear()

    with caplog.at_level(logging.INFO, logger="talentos"):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": _EMAIL,
                "password": _PASSWORD,
                "name": _NAME,
                "accept_privacy": True,
            },
            headers={"X-Correlation-ID": "corr-consent"},
        )

    assert response.status_code == 201
    event = next(
        record
        for record in caplog.records
        if record.getMessage() == "auth_privacy_consent_accepted"
    )
    assert event.request_id == response.headers["X-Request-ID"]
    assert event.correlation_id == "corr-consent"
    assert _EMAIL not in caplog.text
    assert _PASSWORD not in caplog.text
