from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

# Registrar tablas al importar: otras pruebas recargan `app.db.base` y los
# modelos importados después quedarían en una metadata distinta de `Base`.
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
from app.candidates.models import Candidate, CandidateNote, CandidateProfileStatus
from app.candidates.schemas import (
    CandidateCreate,
    CandidateResponse,
    NoteCreate,
    NoteResponse,
)
from app.db.base import Base
from app.identity.models import Organization, User

_PROTECTED_ATTRIBUTES = frozenset(
    {
        "age",
        "birth_date",
        "date_of_birth",
        "disability",
        "gender",
        "marital_status",
        "nationality",
        "photo",
        "religion",
    }
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
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


def _organization_and_author(db: DBSession) -> tuple[Organization, User]:
    org = Organization(name="Org A", slug="candidates-org-a")
    author = User(
        email="author-candidates@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Author",
    )
    db.add_all([org, author])
    db.flush()
    return org, author


def test_profile_status_enum_default_and_utc_timestamps(db: DBSession) -> None:
    org, _author = _organization_and_author(db)
    candidate = Candidate(
        organization_id=org.id, name="Synthetic Candidate", email="candidate@example.test"
    )
    db.add(candidate)
    db.flush()

    assert [status.value for status in CandidateProfileStatus] == [
        "draft",
        "review",
        "confirmed",
        "archived",
    ]
    assert candidate.profile_status is CandidateProfileStatus.DRAFT
    assert candidate.created_at.utcoffset() == timedelta(0)
    assert candidate.updated_at.utcoffset() == timedelta(0)


def test_email_is_not_unique_and_indexes_cover_lookup_fields(db: DBSession) -> None:
    org, _author = _organization_and_author(db)
    first = Candidate(
        organization_id=org.id, name="Synthetic One", email="duplicate@example.test"
    )
    second = Candidate(
        organization_id=org.id, name="Synthetic Two", email="duplicate@example.test"
    )
    db.add_all([first, second])
    db.flush()

    assert len(db.scalars(select(Candidate)).all()) == 2
    candidate_indexes = {index.name for index in Candidate.__table__.indexes}
    note_indexes = {index.name for index in CandidateNote.__table__.indexes}
    assert {
        "ix_candidates_organization_id",
        "ix_candidates_profile_status",
        "ix_candidates_email",
    } <= candidate_indexes
    assert "ix_candidate_notes_candidate_id" in note_indexes


def test_note_is_linked_to_candidate_and_author_and_cascades(db: DBSession) -> None:
    org, author = _organization_and_author(db)
    candidate = Candidate(
        organization_id=org.id, name="Synthetic Candidate", email="candidate@example.test"
    )
    db.add(candidate)
    db.flush()
    note = CandidateNote(candidate_id=candidate.id, author_id=author.id, body="Synthetic note")
    db.add(note)
    db.flush()

    assert note.candidate_id == candidate.id
    assert note.author_id == author.id

    db.delete(candidate)
    db.flush()
    assert db.scalars(select(CandidateNote)).all() == []


def test_note_requires_existing_author(db: DBSession) -> None:
    org, _author = _organization_and_author(db)
    candidate = Candidate(
        organization_id=org.id, name="Synthetic Candidate", email="candidate@example.test"
    )
    db.add(candidate)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                CandidateNote(
                    candidate_id=candidate.id,
                    author_id=uuid.UUID(int=0),
                    body="Synthetic note",
                )
            )
            db.flush()


def test_protected_attributes_are_absent_from_models_and_schemas() -> None:
    model_columns = set(Candidate.__table__.columns.keys())
    note_columns = set(CandidateNote.__table__.columns.keys())
    input_fields = set(CandidateCreate.model_fields) | set(NoteCreate.model_fields)
    response_fields = set(CandidateResponse.model_fields) | set(NoteResponse.model_fields)

    assert not model_columns & _PROTECTED_ATTRIBUTES
    assert not note_columns & _PROTECTED_ATTRIBUTES
    assert not input_fields & _PROTECTED_ATTRIBUTES
    assert not response_fields & _PROTECTED_ATTRIBUTES
    assert "organization_id" not in input_fields
    assert "organization_id" not in response_fields
