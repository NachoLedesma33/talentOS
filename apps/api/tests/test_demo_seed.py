from __future__ import annotations

from collections.abc import Iterator

import email_validator
import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

from app.applications.models import Application
from app.candidates.models import Candidate
from app.db.base import Base
from app.identity.models import Organization, User
from app.identity.service import create_organization, register_user
from app.jobs.models import Job
from scripts.seed_demo import reset_demo, seed_demo

_OTHER_EMAIL = "owner.other@example.test"
_OTHER_PASSWORD = "OtherSynthetic123"


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture
def db_session() -> Iterator[DBSession]:
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with DBSession(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _count(db: DBSession, model: object) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_seed_demo_is_reproducible_and_reset_only_removes_demo(db_session: DBSession) -> None:
    other_user = register_user(
        db_session, email=_OTHER_EMAIL, password=_OTHER_PASSWORD, name="Otro propietario"
    )
    other_org = create_organization(
        db_session, creator=other_user, name="Otra organización", slug="otra-org"
    )

    first = seed_demo(db_session)

    assert first["candidates"] == 3
    assert _count(db_session, Organization) == 2
    assert _count(db_session, Job) == 1
    assert _count(db_session, Candidate) == 3
    assert _count(db_session, Application) == 3

    second = seed_demo(db_session)

    assert second["candidates"] == first["candidates"]
    assert _count(db_session, Organization) == 2
    assert _count(db_session, Job) == 1
    assert _count(db_session, Candidate) == 3
    assert _count(db_session, Application) == 3

    reset_demo(db_session)

    assert _count(db_session, Organization) == 1
    assert _count(db_session, User) == 1
    assert _count(db_session, Job) == 0
    assert _count(db_session, Candidate) == 0
    assert _count(db_session, Application) == 0
    assert db_session.get(Organization, other_org.id) is not None
