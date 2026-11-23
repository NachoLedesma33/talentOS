from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.candidates.models import Candidate
from app.db.base import Base
from app.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
    ExtractedField,
    ExtractedFieldName,
    ExtractedFieldStatus,
    ExtractionStatus,
)
from app.identity.models import Organization, User

_PROTECTED_ATTRIBUTES = frozenset(
    {
        "age",
        "birth_date",
        "birthdate",
        "date_of_birth",
        "disability",
        "ethnicity",
        "gender",
        "marital_status",
        "nationality",
        "photo",
        "photo_url",
        "religion",
        "sexual_orientation",
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


def _seed(db: DBSession) -> tuple[Organization, User, Candidate]:
    org = Organization(name="Org A", slug="documents-org-a")
    user = User(
        email="user-a@example.test", password_hash="synthetic-hash", name="Synthetic User"
    )
    db.add_all([org, user])
    db.flush()
    candidate = Candidate(
        organization_id=org.id,
        name="Synthetic Candidate",
        email="candidate@example.test",
    )
    db.add(candidate)
    db.flush()
    return org, user, candidate


def _document(org: Organization, user: User, candidate: Candidate, name: str) -> Document:
    return Document(
        organization_id=org.id,
        candidate_id=candidate.id,
        uploaded_by=user.id,
        original_filename="synthetic-cv.pdf",
        internal_name=name,
        content_type="application/pdf",
        extension=".pdf",
        size_bytes=8,
        checksum_sha256="0" * 64,
    )


def test_document_related_enums_and_utc_timestamps(db: DBSession) -> None:
    org, user, candidate = _seed(db)
    document = _document(org, user, candidate, "internal-a.pdf")
    db.add(document)
    db.flush()

    assert [item.value for item in DocumentStatus] == [
        "uploaded",
        "processing",
        "processed",
        "failed",
    ]
    assert [item.value for item in ExtractionStatus] == ["pending", "completed", "failed"]
    assert [item.value for item in ExtractedFieldName] == [
        "name",
        "email",
        "location",
        "experience",
        "education",
        "skills",
        "projects",
        "languages",
    ]
    assert [item.value for item in ExtractedFieldStatus] == [
        "extracted",
        "needs_review",
        "missing",
        "confirmed",
        "corrected",
    ]
    assert document.status is DocumentStatus.UPLOADED
    assert document.created_at.utcoffset() == timedelta(0)
    assert document.updated_at.utcoffset() == timedelta(0)


def test_internal_name_is_unique_and_indexes_cover_tenant_lookups(db: DBSession) -> None:
    org, user, candidate = _seed(db)
    db.add(_document(org, user, candidate, "internal-unique.pdf"))
    db.flush()

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(_document(org, user, candidate, "internal-unique.pdf"))
            db.flush()

    assert "uq_documents_internal_name" in {
        item.name for item in Document.__table__.constraints if item.name
    }
    assert {
        "ix_documents_organization_id",
        "ix_documents_candidate_id",
        "ix_documents_status",
        "ix_documents_checksum_sha256",
    } <= {index.name for index in Document.__table__.indexes}
    assert "ix_document_extractions_document_id" in {
        index.name for index in DocumentExtraction.__table__.indexes
    }
    assert "ix_extracted_fields_extraction_id" in {
        index.name for index in ExtractedField.__table__.indexes
    }


def test_extraction_is_unique_per_provider_and_prompt_version(db: DBSession) -> None:
    org, user, candidate = _seed(db)
    document = _document(org, user, candidate, "internal-extraction.pdf")
    db.add(document)
    db.flush()

    def extraction(prompt_version: str) -> DocumentExtraction:
        return DocumentExtraction(
            document_id=document.id,
            provider="mock",
            model="mock-model",
            prompt_version=prompt_version,
            pages=[{"page": 1, "text": "Synthetic text"}],
        )

    first = extraction("v1")
    db.add(first)
    db.flush()
    assert first.status is ExtractionStatus.PENDING

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(extraction("v1"))
            db.flush()

    second = extraction("v2")
    db.add(second)
    db.flush()
    assert second.id != first.id


def test_fields_keep_json_evidence_and_cascade_from_document(db: DBSession) -> None:
    org, user, candidate = _seed(db)
    document = _document(org, user, candidate, "internal-fields.pdf")
    db.add(document)
    db.flush()
    extraction = DocumentExtraction(
        document_id=document.id,
        provider="mock",
        model="mock-model",
        prompt_version="v1",
        pages=[{"page": 1, "text": "Synthetic text", "offsets": [{"start": 0, "end": 14}]}],
    )
    db.add(extraction)
    db.flush()
    evidence = [
        {
            "document_id": str(document.id),
            "page": 1,
            "quote": "Synthetic text",
            "offset": 0,
        }
    ]
    confirmed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    field = ExtractedField(
        extraction_id=extraction.id,
        field_name=ExtractedFieldName.NAME,
        value={"text": "Synthetic Candidate"},
        status=ExtractedFieldStatus.CONFIRMED,
        evidence=evidence,
        confirmed_by=user.id,
        confirmed_at=confirmed_at,
    )
    db.add(field)
    db.commit()
    db.expire_all()

    stored_extraction = db.scalar(
        select(DocumentExtraction).where(DocumentExtraction.id == extraction.id)
    )
    stored_field = db.scalar(select(ExtractedField).where(ExtractedField.id == field.id))
    assert stored_extraction is not None
    assert stored_field is not None
    assert stored_extraction.pages[0]["page"] == 1
    assert stored_field.evidence == evidence
    assert stored_field.confirmed_by == user.id
    # SQLite round-trip pierde el tzinfo; el valor se guardó como UTC y se compara como tal.
    assert stored_field.confirmed_at is not None
    assert stored_field.confirmed_at.replace(tzinfo=UTC) == confirmed_at

    db.delete(document)
    db.commit()
    assert db.scalars(select(DocumentExtraction)).all() == []
    assert db.scalars(select(ExtractedField)).all() == []


def test_document_models_do_not_include_protected_attributes() -> None:
    for model in (Document, DocumentExtraction, ExtractedField):
        columns = set(model.__table__.columns.keys())
        assert columns.isdisjoint(_PROTECTED_ATTRIBUTES)
