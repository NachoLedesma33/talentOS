from __future__ import annotations

import importlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.identity.models  # noqa: F401  # registra las tablas antes de create_all
from app.core.config import get_settings
from app.db import base as base_module
from app.db.base import Base
from app.db.session import get_db
from app.identity.models import Session as UserSession
from app.identity.models import User
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
