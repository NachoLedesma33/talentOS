from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import email_validator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.audit.models  # noqa: F401  # registra audit_log en Base.metadata
import app.identity.models  # noqa: F401  # registra identity en Base.metadata
from app.audit.models import AuditLog
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.identity.models import Invitation, Membership, MembershipRole, User
from app.identity.security import hash_token
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


def _register(client: TestClient, email: str, name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "name": name},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text


def _create_org(client: TestClient, name: str, slug: str) -> dict[str, object]:
    response = client.post(_ORG_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()


def _org_headers(org_id: object) -> dict[str, str]:
    return {"X-Organization-ID": str(org_id)}


def test_create_organization_assigns_owner_and_audits(client: TestClient, db: DBSession) -> None:
    owner_email = "owner-org@example.test"
    owner_id = _register(client, owner_email, "Synthetic Owner")
    _login(client, owner_email)

    organization = _create_org(client, "Synthetic Org", "synthetic-org")

    organization_id = UUID(str(organization["id"]))
    actor_id = UUID(owner_id)
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == actor_id,
        )
    )
    assert membership is not None
    assert membership.role is MembershipRole.OWNER
    audit = db.scalar(select(AuditLog))
    assert audit is not None
    assert audit.organization_id == organization_id
    assert audit.actor_id == actor_id
    assert audit.action == "organization.created"


def test_list_organizations_only_returns_users_memberships(client: TestClient) -> None:
    email_a = "owner-a@example.test"
    email_b = "owner-b@example.test"
    _register(client, email_a, "Owner A")
    _login(client, email_a)
    org_a = _create_org(client, "Org A", "org-a")
    _register(client, email_b, "Owner B")
    _login(client, email_b)
    org_b = _create_org(client, "Org B", "org-b")

    _login(client, email_a)
    response_a = client.get(_ORG_URL)
    _login(client, email_b)
    response_b = client.get(_ORG_URL)

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert [item["id"] for item in response_a.json()] == [org_a["id"]]
    assert [item["id"] for item in response_b.json()] == [org_b["id"]]


def test_member_listing_is_scoped_to_active_organization(client: TestClient) -> None:
    email_a = "owner-a@example.test"
    email_b = "owner-b@example.test"
    _register(client, email_a, "Owner A")
    _login(client, email_a)
    org_a = _create_org(client, "Org A", "org-a")
    _register(client, email_b, "Owner B")
    _login(client, email_b)
    org_b = _create_org(client, "Org B", "org-b")
    _login(client, email_a)

    own = client.get(f"{_ORG_URL}{org_a['id']}/members", headers=_org_headers(org_a["id"]))
    foreign_header = client.get(
        f"{_ORG_URL}{org_a['id']}/members", headers=_org_headers(org_b["id"])
    )
    foreign_path = client.get(
        f"{_ORG_URL}{org_b['id']}/members", headers=_org_headers(org_a["id"])
    )

    assert own.status_code == 200
    assert [item["email"] for item in own.json()] == [email_a]
    assert foreign_header.status_code == 403
    assert foreign_path.status_code == 404


def test_user_from_org_a_cannot_modify_org_b(client: TestClient, db: DBSession) -> None:
    email_a = "owner-a@example.test"
    email_b = "owner-b@example.test"
    invitee = "invitee-org@example.test"
    _register(client, email_a, "Owner A")
    _login(client, email_a)
    org_a = _create_org(client, "Org A", "org-a")
    _register(client, email_b, "Owner B")
    _login(client, email_b)
    org_b = _create_org(client, "Org B", "org-b")
    owner_b_id = str(db.scalar(select(User.id).where(User.email == email_b)))
    _register(client, invitee, "Invitee")
    _login(client, email_a)

    invite = client.post(
        f"{_ORG_URL}{org_b['id']}/members",
        json={"email": invitee, "role": "viewer"},
        headers=_org_headers(org_a["id"]),
    )
    change_role = client.patch(
        f"{_ORG_URL}{org_b['id']}/members/{owner_b_id}",
        json={"role": "viewer"},
        headers=_org_headers(org_a["id"]),
    )

    assert invite.status_code == 404
    assert change_role.status_code == 404
    assert len(db.scalars(select(Membership)).all()) == 2
    assert db.scalars(select(AuditLog.action)).all() == [
        "organization.created",
        "organization.created",
    ]


def test_admin_can_invite_but_cannot_demote_last_owner(client: TestClient) -> None:
    owner_email = "owner-org@example.test"
    admin_email = "admin-org@example.test"
    invitee = "invitee-org@example.test"
    second_invitee = "second-invitee@example.test"
    owner_id = _register(client, owner_email, "Owner")
    _register(client, admin_email, "Admin")
    _register(client, invitee, "Invitee")
    _register(client, second_invitee, "Second Invitee")
    _login(client, owner_email)
    org = _create_org(client, "Org", "org")
    headers = _org_headers(org["id"])
    admin_invite = client.post(
        f"{_ORG_URL}{org['id']}/members",
        json={"email": admin_email, "role": "admin"},
        headers=headers,
    )
    assert admin_invite.status_code == 201

    _login(client, admin_email)
    invited = client.post(
        f"{_ORG_URL}{org['id']}/members",
        json={"email": second_invitee, "role": "viewer"},
        headers=headers,
    )
    demote_owner = client.patch(
        f"{_ORG_URL}{org['id']}/members/{owner_id}",
        json={"role": "viewer"},
        headers=headers,
    )
    escalate_owner = client.post(
        f"{_ORG_URL}{org['id']}/members",
        json={"email": invitee, "role": "owner"},
        headers=headers,
    )
    change_viewer = client.patch(
        f"{_ORG_URL}{org['id']}/members/{invited.json()['user_id']}",
        json={"role": "reviewer"},
        headers=headers,
    )

    assert invited.status_code == 201
    assert demote_owner.status_code == 409
    assert escalate_owner.status_code == 403
    assert change_viewer.status_code == 200
    assert change_viewer.json()["role"] == "reviewer"


def test_audit_contains_events_with_actor_and_no_secrets(client: TestClient, db: DBSession) -> None:
    owner_email = "owner-org@example.test"
    member_email = "member-org@example.test"
    owner_id = _register(client, owner_email, "Owner")
    _register(client, member_email, "Member")
    _login(client, owner_email)
    org = _create_org(client, "Org", "org")
    headers = _org_headers(org["id"])
    assert client.post(
        f"{_ORG_URL}{org['id']}/members",
        json={"email": member_email, "role": "viewer"},
        headers=headers,
    ).status_code == 201
    member_id = str(db.scalar(select(User.id).where(User.email == member_email)))
    assert client.patch(
        f"{_ORG_URL}{org['id']}/members/{member_id}",
        json={"role": "reviewer"},
        headers=headers,
    ).status_code == 200

    organization_id = UUID(str(org["id"]))
    actor_id = UUID(owner_id)
    events = db.scalars(select(AuditLog).order_by(AuditLog.timestamp)).all()
    assert [event.action for event in events] == [
        "organization.created",
        "member.invited",
        "member.role_changed",
    ]
    assert all(event.organization_id == organization_id for event in events)
    assert all(event.actor_id == actor_id for event in events)
    columns = {column.name for column in AuditLog.__table__.columns}
    assert columns == {
        "id",
        "organization_id",
        "actor_id",
        "action",
        "resource_type",
        "resource_id",
        "timestamp",
    }
    for event in events:
        row_text = str([getattr(event, name) for name in columns])
        assert owner_email not in row_text
        assert member_email not in row_text
        assert _PASSWORD not in row_text


def test_duplicate_slug_and_duplicate_member_return_409(client: TestClient) -> None:
    owner_email = "owner-org@example.test"
    member_email = "member-org@example.test"
    _register(client, owner_email, "Owner")
    _register(client, member_email, "Member")
    _login(client, owner_email)
    org = _create_org(client, "Org", "org")
    headers = _org_headers(org["id"])
    assert client.post(_ORG_URL, json={"name": "Other", "slug": "org"}).status_code == 409
    invite_payload = {"email": member_email, "role": "viewer"}
    assert client.post(
        f"{_ORG_URL}{org['id']}/members", json=invite_payload, headers=headers
    ).status_code == 201
    assert client.post(
        f"{_ORG_URL}{org['id']}/members", json=invite_payload, headers=headers
    ).status_code == 409


def _invite(
    client: TestClient,
    org_id: object,
    email: str,
    role: str = "viewer",
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"{_ORG_URL}{org_id}/invitations",
        json={"email": email, "role": role},
        headers=headers if headers is not None else _org_headers(org_id),
    )


def test_invitation_creation_returns_demo_token_and_audits(
    client: TestClient, db: DBSession
) -> None:
    owner_email = "owner-invite@example.test"
    invitee_email = "invitee-invite@example.test"
    _register(client, owner_email, "Owner")
    _register(client, invitee_email, "Invitee")
    _login(client, owner_email)
    org = _create_org(client, "Invite Org", "invite-org")

    response = _invite(client, org["id"], invitee_email)

    assert response.status_code == 201
    token = response.json()["dev_token"]
    assert token
    stored = db.scalar(select(Invitation.token_hash))
    assert stored == hash_token(token)
    assert stored != token
    invitation = db.scalar(select(Invitation))
    assert invitation is not None
    assert invitation.email == invitee_email
    assert invitation.role is MembershipRole.VIEWER
    assert invitation.organization_id == UUID(str(org["id"]))
    assert db.scalars(select(AuditLog.action).order_by(AuditLog.timestamp)).all() == [
        "organization.created",
        "invitation.created",
    ]


def test_invitation_preview_is_public_and_hides_unknown_tokens(client: TestClient) -> None:
    owner_email = "owner-preview@example.test"
    invitee_email = "invitee-preview@example.test"
    _register(client, owner_email, "Owner")
    _register(client, invitee_email, "Invitee")
    _login(client, owner_email)
    org = _create_org(client, "Preview Org", "preview-org")
    token = _invite(client, org["id"], invitee_email).json()["dev_token"]
    client.cookies.clear()

    preview = client.get(f"{_ORG_URL}invitations/{token}")
    missing = client.get(f"{_ORG_URL}invitations/not-a-real-token")

    assert preview.status_code == 200
    body = preview.json()
    assert body["organization_name"] == "Preview Org"
    assert body["email"] == invitee_email
    assert body["role"] == "viewer"
    assert "token" not in body
    assert missing.status_code == 404


def test_invitation_accept_creates_membership_and_consumes_token(
    client: TestClient, db: DBSession
) -> None:
    owner_email = "owner-accept@example.test"
    invitee_email = "invitee-accept@example.test"
    _register(client, owner_email, "Owner")
    invitee_id = _register(client, invitee_email, "Invitee")
    _login(client, owner_email)
    org = _create_org(client, "Accept Org", "accept-org")
    token = _invite(client, org["id"], invitee_email).json()["dev_token"]

    _login(client, invitee_email)
    response = client.post(f"{_ORG_URL}invitations/{token}/accept")

    assert response.status_code == 200
    assert response.json() == {
        "organization_id": org["id"],
        "organization_name": "Accept Org",
        "role": "viewer",
    }
    invitation = db.scalar(select(Invitation))
    assert invitation is not None
    assert invitation.accepted_at is not None
    membership = db.scalar(
        select(Membership).where(Membership.user_id == UUID(invitee_id))
    )
    assert membership is not None
    assert db.scalars(select(AuditLog.action).order_by(AuditLog.timestamp)).all() == [
        "organization.created",
        "invitation.created",
        "invitation.accepted",
    ]
    assert client.get(f"{_ORG_URL}invitations/{token}").status_code == 404
    assert client.post(f"{_ORG_URL}invitations/{token}/accept").status_code == 404


def test_invitation_accept_rejects_email_mismatch(client: TestClient, db: DBSession) -> None:
    owner_email = "owner-mismatch@example.test"
    invitee_email = "invitee-mismatch@example.test"
    other_email = "other-mismatch@example.test"
    _register(client, owner_email, "Owner")
    _register(client, invitee_email, "Invitee")
    _register(client, other_email, "Other")
    _login(client, owner_email)
    org = _create_org(client, "Mismatch Org", "mismatch-org")
    token = _invite(client, org["id"], invitee_email).json()["dev_token"]

    _login(client, other_email)
    response = client.post(f"{_ORG_URL}invitations/{token}/accept")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert len(db.scalars(select(Membership)).all()) == 1


def test_invitation_expired_and_replayed_tokens_are_rejected(
    client: TestClient, db: DBSession
) -> None:
    owner_email = "owner-expired@example.test"
    invitee_email = "invitee-expired@example.test"
    _register(client, owner_email, "Owner")
    _register(client, invitee_email, "Invitee")
    _login(client, owner_email)
    org = _create_org(client, "Expired Org", "expired-org")
    expired_token = _invite(client, org["id"], invitee_email).json()["dev_token"]
    invitation = db.scalar(select(Invitation))
    assert invitation is not None
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    valid_token = _invite(client, org["id"], invitee_email).json()["dev_token"]

    _login(client, invitee_email)
    expired = client.post(f"{_ORG_URL}invitations/{expired_token}/accept")
    accepted = client.post(f"{_ORG_URL}invitations/{valid_token}/accept")
    replayed = client.post(f"{_ORG_URL}invitations/{valid_token}/accept")

    assert expired.status_code == 404
    assert accepted.status_code == 200
    assert replayed.status_code == 404


def test_invitation_creation_is_scoped_to_active_organization(client: TestClient) -> None:
    email_a = "owner-invite-a@example.test"
    email_b = "owner-invite-b@example.test"
    invitee_email = "invitee-scoped@example.test"
    _register(client, email_a, "Owner A")
    _login(client, email_a)
    org_a = _create_org(client, "Org A", "invite-a")
    _register(client, email_b, "Owner B")
    _register(client, invitee_email, "Invitee")
    _login(client, email_b)
    org_b = _create_org(client, "Org B", "invite-b")
    _login(client, email_a)

    foreign_header = _invite(
        client, org_a["id"], invitee_email, headers=_org_headers(org_b["id"])
    )
    foreign_path = _invite(
        client, org_b["id"], invitee_email, headers=_org_headers(org_a["id"])
    )
    own = _invite(client, org_a["id"], invitee_email)

    assert foreign_header.status_code == 403
    assert foreign_path.status_code == 404
    assert own.status_code == 201
