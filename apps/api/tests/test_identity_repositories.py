from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession

from app.db.base import Base

if TYPE_CHECKING:
    from app.identity.models import Organization, User


@pytest.fixture
def engine() -> Iterator[Engine]:
    import app.identity.models  # noqa: F401  # registra tablas antes de create_all

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def tenants(db: DBSession) -> tuple[Organization, Organization, User, User]:
    from app.identity.models import Membership, MembershipRole, Organization, User

    org_a = Organization(name="Org A", slug="org-a")
    org_b = Organization(name="Org B", slug="org-b")
    user_a = User(email="user-a@example.test", password_hash="synthetic-hash", name="User A")
    user_b = User(email="user-b@example.test", password_hash="synthetic-hash", name="User B")
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    db.add_all(
        [
            Membership(organization_id=org_a.id, user_id=user_a.id, role=MembershipRole.OWNER),
            Membership(organization_id=org_b.id, user_id=user_b.id, role=MembershipRole.VIEWER),
        ]
    )
    db.flush()
    return org_a, org_b, user_a, user_b


def test_get_membership_does_not_return_other_organization(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.identity.repositories import get_membership

    org_a, org_b, user_a, _ = tenants

    own_membership = get_membership(db, user_a.id, org_a.id)
    foreign_membership = get_membership(db, user_a.id, org_b.id)

    assert own_membership is not None
    assert own_membership.role.value == "owner"
    assert foreign_membership is None


def test_list_organization_members_is_tenant_scoped(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.identity.repositories import list_organization_members

    org_a, org_b, user_a, user_b = tenants

    members_a = list_organization_members(db, org_a.id)
    members_b = list_organization_members(db, org_b.id)

    assert [member.user_id for member in members_a] == [user_a.id]
    assert [member.user_id for member in members_b] == [user_b.id]
    assert all(member.organization_id == org_a.id for member in members_a)
    assert all(member.organization_id == org_b.id for member in members_b)


def test_user_belongs_to_organization_false_for_foreign_org(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.identity.repositories import user_belongs_to_organization

    org_a, org_b, user_a, user_b = tenants

    assert user_belongs_to_organization(db, user_a.id, org_a.id) is True
    assert user_belongs_to_organization(db, user_a.id, org_b.id) is False
    assert user_belongs_to_organization(db, user_b.id, org_a.id) is False


def test_get_user_by_email_is_tenant_scoped(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.identity.repositories import get_user_by_email

    org_a, org_b, _, user_b = tenants

    own_user = get_user_by_email(db, "USER-B@example.test", org_b.id)
    foreign_user = get_user_by_email(db, "user-b@example.test", org_a.id)

    assert own_user is not None
    assert own_user.id == user_b.id
    assert foreign_user is None


def test_repositories_do_not_create_rows(
    db: DBSession, tenants: tuple[Organization, Organization, User, User]
) -> None:
    from app.identity.models import Session as UserSession
    from app.identity.models import User
    from app.identity.repositories import (
        get_membership,
        get_user_by_email,
        list_organization_members,
        user_belongs_to_organization,
    )

    org_a, _, user_a, _ = tenants
    before_users = len(db.scalars(select(User)).all())
    before_sessions = len(db.scalars(select(UserSession)).all())

    get_membership(db, user_a.id, org_a.id)
    get_user_by_email(db, "user-a@example.test", org_a.id)
    user_belongs_to_organization(db, user_a.id, org_a.id)
    list_organization_members(db, org_a.id)

    assert len(db.scalars(select(User)).all()) == before_users
    assert len(db.scalars(select(UserSession)).all()) == before_sessions
