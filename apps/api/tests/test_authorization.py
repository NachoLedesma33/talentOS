from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import email_validator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.audit.models  # noqa: F401  # registra audit_log en Base.metadata
import app.identity.models  # noqa: F401  # registra identity en Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME
_ORG_URL = "/api/v1/organizations/"


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """EmailStr rechaza `.test` salvo en entorno de pruebas explícito."""
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


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


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORG_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_no_cookie_returns_401_on_private_routes(client: TestClient) -> None:
    response_list = client.get(_ORG_URL)
    response_members = client.get(
        f"{_ORG_URL}{uuid4()}/members", headers={"X-Organization-ID": str(uuid4())}
    )

    assert response_list.status_code == 401
    assert response_list.json()["error"]["code"] == "unauthorized"
    assert response_members.status_code == 401


def test_invalid_missing_and_foreign_organization_header_returns_403(client: TestClient) -> None:
    owner_email = "owner-auth@example.test"
    foreign_email = "foreign-auth@example.test"
    _register(client, owner_email, "Owner")
    _login(client, owner_email)
    org_id = _create_org(client, "Org", "org")
    _register(client, foreign_email, "Foreign")
    _login(client, foreign_email)
    foreign_org_id = _create_org(client, "Foreign Org", "foreign-org")
    _login(client, owner_email)

    invalid = client.get(f"{_ORG_URL}{org_id}/members", headers={"X-Organization-ID": "not-a-uuid"})
    missing = client.get(f"{_ORG_URL}{org_id}/members")
    foreign = client.get(
        f"{_ORG_URL}{org_id}/members", headers={"X-Organization-ID": foreign_org_id}
    )

    assert invalid.status_code == 403
    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert invalid.json()["error"]["code"] == "forbidden"
    assert invalid.json()["error"]["message"] == "Organización no disponible."


def test_viewer_can_read_members_but_cannot_invite_or_change_roles(client: TestClient) -> None:
    owner_email = "owner-auth@example.test"
    viewer_email = "viewer-auth@example.test"
    extra_email = "extra-auth@example.test"
    _register(client, owner_email, "Owner")
    _register(client, viewer_email, "Viewer")
    _register(client, extra_email, "Extra")
    _login(client, owner_email)
    org_id = _create_org(client, "Org", "org")
    headers = {"X-Organization-ID": org_id}
    assert client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": viewer_email, "role": "viewer"},
        headers=headers,
    ).status_code == 201

    _login(client, viewer_email)
    read = client.get(f"{_ORG_URL}{org_id}/members", headers=headers)
    invite = client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": extra_email, "role": "viewer"},
        headers=headers,
    )
    change_owner = client.patch(
        f"{_ORG_URL}{org_id}/members/{read.json()[0]['user_id']}",
        json={"role": "admin"},
        headers=headers,
    )

    assert read.status_code == 200
    assert invite.status_code == 403
    assert change_owner.status_code == 403


def test_recruiter_cannot_manage_members(client: TestClient) -> None:
    owner_email = "owner-auth@example.test"
    recruiter_email = "recruiter-auth@example.test"
    extra_email = "extra-recruiter@example.test"
    _register(client, owner_email, "Owner")
    _register(client, recruiter_email, "Recruiter")
    _register(client, extra_email, "Extra")
    _login(client, owner_email)
    org_id = _create_org(client, "Org", "org")
    headers = {"X-Organization-ID": org_id}
    assert client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": recruiter_email, "role": "recruiter"},
        headers=headers,
    ).status_code == 201

    _login(client, recruiter_email)
    invite = client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": extra_email, "role": "viewer"},
        headers=headers,
    )
    read_members = client.get(f"{_ORG_URL}{org_id}/members", headers=headers)
    own_orgs = client.get(_ORG_URL)

    assert invite.status_code == 403
    assert read_members.status_code == 403
    assert own_orgs.status_code == 200


def test_reviewer_cannot_manage_members(client: TestClient) -> None:
    owner_email = "owner-auth@example.test"
    reviewer_email = "reviewer-auth@example.test"
    extra_email = "extra-reviewer@example.test"
    _register(client, owner_email, "Owner")
    _register(client, reviewer_email, "Reviewer")
    _register(client, extra_email, "Extra")
    _login(client, owner_email)
    org_id = _create_org(client, "Org", "org")
    headers = {"X-Organization-ID": org_id}
    assert client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": reviewer_email, "role": "reviewer"},
        headers=headers,
    ).status_code == 201

    _login(client, reviewer_email)
    invite = client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": extra_email, "role": "viewer"},
        headers=headers,
    )
    read_members = client.get(f"{_ORG_URL}{org_id}/members", headers=headers)

    assert invite.status_code == 403
    assert read_members.status_code == 200


def test_foreign_origin_cannot_write_organization_or_members(client: TestClient) -> None:
    owner_email = "owner-auth@example.test"
    member_email = "member-auth@example.test"
    _register(client, owner_email, "Owner")
    _register(client, member_email, "Member")
    _login(client, owner_email)
    headers = {"Origin": "https://foreign.example"}

    org_response = client.post(
        _ORG_URL, json={"name": "Org", "slug": "org"}, headers=headers
    )
    org_id = _create_org(client, "Allowed Org", "allowed-org")
    member_response = client.post(
        f"{_ORG_URL}{org_id}/members",
        json={"email": member_email, "role": "viewer"},
        headers={**headers, "X-Organization-ID": org_id},
    )

    assert org_response.status_code == 403
    assert member_response.status_code == 403
