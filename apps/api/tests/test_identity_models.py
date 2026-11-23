from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.db.base import Base

if TYPE_CHECKING:
    from app.identity.models import Membership, MembershipRole, Organization, User


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


def _user(email: str) -> User:
    from app.identity.models import User

    return User(email=email, password_hash="synthetic-hash", name="Synthetic User")


def _organization(name: str, slug: str) -> Organization:
    from app.identity.models import Organization

    return Organization(name=name, slug=slug)


def _membership(organization: Organization, user: User, role: MembershipRole) -> Membership:
    from app.identity.models import Membership

    return Membership(organization_id=organization.id, user_id=user.id, role=role)


def _reject_duplicate(db: DBSession, entity: object) -> None:
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(entity)
            db.flush()


def test_email_slug_and_membership_are_unique(db: DBSession) -> None:
    from app.identity.models import MembershipRole, Organization, User

    org_a = _organization("Org A", "org-a")
    org_b = _organization("Org B", "org-b")
    user_a = _user("user-a@example.test")
    user_b = _user("user-b@example.test")
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    db.add_all(
        [
            _membership(org_a, user_a, MembershipRole.OWNER),
            _membership(org_b, user_b, MembershipRole.OWNER),
        ]
    )
    db.flush()

    _reject_duplicate(db, _user("USER-A@example.test"))
    _reject_duplicate(db, _organization("Org A copy", "org-a"))
    _reject_duplicate(db, _membership(org_a, user_a, MembershipRole.VIEWER))

    assert len(db.scalars(select(User)).all()) == 2
    assert len(db.scalars(select(Organization)).all()) == 2


def test_email_is_normalized_to_lowercase(db: DBSession) -> None:
    user = _user(" USER-A@EXAMPLE.TEST ")

    db.add(user)
    db.flush()

    assert user.email == "user-a@example.test"


def test_status_and_role_use_declared_enum_values(db: DBSession) -> None:
    from app.identity.models import Membership, MembershipRole, User, UserStatus

    assert [status.value for status in UserStatus] == ["active", "inactive"]
    assert [role.value for role in MembershipRole] == [
        "owner",
        "admin",
        "recruiter",
        "reviewer",
        "viewer",
    ]

    org = _organization("Org A", "org-a")
    user = _user("user-a@example.test")
    user.status = UserStatus.INACTIVE
    db.add_all([org, user])
    db.flush()
    membership = _membership(org, user, MembershipRole.REVIEWER)
    db.add(membership)
    db.flush()

    stored_status = db.scalar(select(User.status).where(User.id == user.id))
    stored_role = db.scalar(select(Membership.role).where(Membership.id == membership.id))
    assert stored_status is UserStatus.INACTIVE
    assert stored_role is MembershipRole.REVIEWER


def test_timestamps_default_to_utc(db: DBSession) -> None:
    user = _user("user-a@example.test")

    db.add(user)
    db.flush()

    assert user.created_at.tzinfo is not None
    assert user.created_at.utcoffset() == timedelta(0)
    assert user.updated_at.tzinfo is not None
    assert user.updated_at.utcoffset() == timedelta(0)


def test_deleting_user_cascades_their_sessions(db: DBSession) -> None:
    from app.identity.models import Session as UserSession

    user = _user("user-a@example.test")
    db.add(user)
    db.flush()
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    sessions = [
        UserSession(user_id=user.id, token_hash=f"hash-{index}", expires_at=expires_at)
        for index in range(2)
    ]
    db.add_all(sessions)
    db.flush()
    assert len(db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()) == 2

    db.delete(user)
    db.flush()

    assert db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all() == []
