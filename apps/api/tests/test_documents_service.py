from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session as DBSession

from app.audit.models import AuditLog
from app.audit.service import list_resource_events
from app.candidates.models import Candidate
from app.db.base import Base
from app.documents import storage as storage_module
from app.documents.models import Document, DocumentStatus
from app.documents.repositories import count_documents
from app.documents.repositories import get_document as get_document_row
from app.documents.repositories import list_documents as list_document_rows
from app.documents.service import (
    DocumentNotFoundError,
    create_document,
    delete_document,
    get_document,
    list_documents,
)
from app.documents.storage import DocumentStorageError
from app.documents.validation import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME,
    MAX_PAGES,
    MAX_SIZE_BYTES,
    UploadValidationError,
    validate_upload,
)
from app.identity.models import Membership, MembershipRole, Organization, User


@dataclass(frozen=True)
class _Tenant:
    org: Organization
    user: User
    candidate: Candidate


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


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "var" / "documents"
    monkeypatch.setattr(storage_module, "_base_dir", lambda: root)
    return root


@pytest.fixture
def tenants(db: DBSession) -> tuple[_Tenant, _Tenant]:
    org_a = Organization(name="Org A", slug="documents-service-org-a")
    org_b = Organization(name="Org B", slug="documents-service-org-b")
    user_a = User(
        email="user-a@example.test", password_hash="synthetic-hash", name="Synthetic User A"
    )
    user_b = User(
        email="user-b@example.test", password_hash="synthetic-hash", name="Synthetic User B"
    )
    db.add_all([org_a, org_b, user_a, user_b])
    db.flush()
    db.add_all(
        [
            Membership(organization_id=org_a.id, user_id=user_a.id, role=MembershipRole.OWNER),
            Membership(organization_id=org_b.id, user_id=user_b.id, role=MembershipRole.OWNER),
        ]
    )
    candidate_a = Candidate(
        organization_id=org_a.id,
        name="Synthetic Candidate A",
        email="candidate-a@example.test",
    )
    candidate_b = Candidate(
        organization_id=org_b.id,
        name="Synthetic Candidate B",
        email="candidate-b@example.test",
    )
    db.add_all([candidate_a, candidate_b])
    db.commit()
    return (
        _Tenant(org_a, user_a, candidate_a),
        _Tenant(org_b, user_b, candidate_b),
    )


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document><w:body>Synthetic</w:body></w:document>")
        archive.writestr("[Content_Types].xml", "<Types/>")
    return buffer.getvalue()


def test_synthetic_pdf_and_docx_pass_validation() -> None:
    assert ALLOWED_EXTENSIONS == frozenset({".pdf", ".docx"})
    assert ALLOWED_MIME[".pdf"] == "application/pdf"
    assert ALLOWED_MIME[".docx"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert MAX_SIZE_BYTES == 10 * 1024 * 1024
    assert MAX_PAGES == 50

    validate_upload(filename="synthetic-cv.pdf", content_type="application/pdf", data=_pdf_bytes())
    validate_upload(
        filename="synthetic-cv.docx",
        content_type=ALLOWED_MIME[".docx"],
        data=_docx_bytes(),
    )


@pytest.mark.parametrize(
    ("filename", "content_type", "data", "expected"),
    [
        ("synthetic-cv.txt", "application/pdf", _pdf_bytes(), "invalid_extension"),
        ("synthetic-cv.pdf", "text/plain", _pdf_bytes(), "invalid_mime"),
        ("synthetic-cv.pdf", "application/pdf", b"not a pdf", "invalid_signature"),
        (
            "synthetic-cv.docx",
            ALLOWED_MIME[".docx"],
            _pdf_bytes(),
            "invalid_signature",
        ),
        ("synthetic-cv.pdf", "application/pdf", b"", "empty_file"),
        (
            "synthetic-cv.pdf",
            "application/pdf",
            b"%PDF-" + b"0" * MAX_SIZE_BYTES,
            "too_large",
        ),
    ],
)
def test_invalid_uploads_fail_with_stable_codes_without_payload(
    filename: str, content_type: str, data: bytes, expected: str
) -> None:
    with pytest.raises(UploadValidationError) as exc:
        validate_upload(filename=filename, content_type=content_type, data=data)

    assert exc.value.code == expected
    assert expected in str(exc.value)
    assert "synthetic-cv" not in str(exc.value)
    assert "not a pdf" not in str(exc.value)


def test_create_document_stores_checksum_metadata_and_unpredictable_name(
    db: DBSession, storage_root: Path, tenants: tuple[_Tenant, _Tenant]
) -> None:
    tenant = tenants[0]
    payload = _pdf_bytes()

    document = create_document(
        db,
        organization_id=tenant.org.id,
        candidate_id=tenant.candidate.id,
        uploader_id=tenant.user.id,
        filename="synthetic-cv.pdf",
        content_type="application/pdf",
        data=payload,
    )

    assert document.status is DocumentStatus.UPLOADED
    assert document.organization_id == tenant.org.id
    assert document.candidate_id == tenant.candidate.id
    assert document.uploaded_by == tenant.user.id
    assert document.original_filename == "synthetic-cv.pdf"
    assert document.size_bytes == len(payload)
    assert document.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,}\.pdf", document.internal_name)
    assert "synthetic-cv" not in document.internal_name

    stored = storage_root / str(tenant.org.id) / str(document.id) / document.internal_name
    assert stored.read_bytes() == payload

    events = list_resource_events(db, tenant.org.id, "document", document.id)
    assert [event.action for event in events] == ["document.uploaded"]
    assert all(event.actor_id == tenant.user.id for event in events)
    assert "payload" not in AuditLog.__table__.columns
    assert "data" not in AuditLog.__table__.columns
    for audit_event in events:
        values = " ".join(
            str(value) for key, value in vars(audit_event).items() if not key.startswith("_")
        )
        assert "synthetic-cv" not in values
        assert "synthetic" not in values.lower()


def test_create_document_accepts_docx(
    db: DBSession, storage_root: Path, tenants: tuple[_Tenant, _Tenant]
) -> None:
    owner = tenants[0]
    payload = _docx_bytes()

    document = create_document(
        db,
        organization_id=owner.org.id,
        candidate_id=owner.candidate.id,
        uploader_id=owner.user.id,
        filename="synthetic-cv.docx",
        content_type=ALLOWED_MIME[".docx"],
        data=payload,
    )

    assert document.extension == ".docx"
    assert document.content_type == ALLOWED_MIME[".docx"]
    assert document.internal_name.endswith(".docx")
    assert document.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    stored = storage_root / str(owner.org.id) / str(document.id) / document.internal_name
    assert stored.read_bytes() == payload


def test_cross_tenant_get_list_and_delete_do_not_expose_documents(
    db: DBSession, storage_root: Path, tenants: tuple[_Tenant, _Tenant]
) -> None:
    owner, outsider = tenants
    document = create_document(
        db,
        organization_id=owner.org.id,
        candidate_id=owner.candidate.id,
        uploader_id=owner.user.id,
        filename="synthetic-cv.pdf",
        content_type="application/pdf",
        data=_pdf_bytes(),
    )
    stored = storage_root / str(owner.org.id) / str(document.id) / document.internal_name

    with pytest.raises(DocumentNotFoundError) as exc:
        get_document(db, organization_id=outsider.org.id, document_id=document.id)
    assert exc.value.code == "not_found"
    assert get_document_row(db, outsider.org.id, document.id) is None

    documents, total = list_documents(db, organization_id=outsider.org.id)
    assert documents == []
    assert total == 0
    assert list_document_rows(db, outsider.org.id) == []
    assert count_documents(db, outsider.org.id) == 0

    with pytest.raises(DocumentNotFoundError):
        delete_document(db, organization_id=outsider.org.id, document_id=document.id)

    assert get_document(db, organization_id=owner.org.id, document_id=document.id).id == document.id
    assert stored.exists()


def test_candidate_and_uploader_must_belong_to_organization(
    db: DBSession, storage_root: Path, tenants: tuple[_Tenant, _Tenant]
) -> None:
    owner, outsider = tenants
    payload = _pdf_bytes()

    with pytest.raises(DocumentNotFoundError) as exc:
        create_document(
            db,
            organization_id=owner.org.id,
            candidate_id=outsider.candidate.id,
            uploader_id=owner.user.id,
            filename="synthetic-cv.pdf",
            content_type="application/pdf",
            data=payload,
        )
    assert exc.value.code == "not_found"

    with pytest.raises(DocumentNotFoundError):
        create_document(
            db,
            organization_id=owner.org.id,
            candidate_id=owner.candidate.id,
            uploader_id=outsider.user.id,
            filename="synthetic-cv.pdf",
            content_type="application/pdf",
            data=payload,
        )

    assert db.scalars(select(Document)).all() == []


def test_storage_write_failure_leaves_no_document_row(
    db: DBSession,
    storage_root: Path,
    tenants: tuple[_Tenant, _Tenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = tenants[0]

    def fail(**_kwargs: object) -> None:
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(storage_module, "store_document", fail)

    with pytest.raises(DocumentStorageError) as exc:
        create_document(
            db,
            organization_id=owner.org.id,
            candidate_id=owner.candidate.id,
            uploader_id=owner.user.id,
            filename="synthetic-cv.pdf",
            content_type="application/pdf",
            data=_pdf_bytes(),
        )

    assert exc.value.code == "storage_unavailable"
    assert db.scalars(select(Document)).all() == []
    assert db.scalars(select(AuditLog)).all() == []


def test_storage_rejects_internal_name_outside_private_directory(
    db: DBSession, storage_root: Path, tenants: tuple[_Tenant, _Tenant]
) -> None:
    owner = tenants[0]
    with pytest.raises(DocumentStorageError) as exc:
        storage_module.store_document(
            organization_id=owner.org.id,
            document_id=owner.candidate.id,
            internal_name="../escape.pdf",
            data=_pdf_bytes(),
        )

    assert exc.value.code == "invalid_storage_key"
    assert not (storage_root.parent / "escape.pdf").exists()


def test_delete_document_removes_bytes_row_and_audits(
    db: DBSession, storage_root: Path, tenants: tuple[_Tenant, _Tenant]
) -> None:
    owner = tenants[0]
    document = create_document(
        db,
        organization_id=owner.org.id,
        candidate_id=owner.candidate.id,
        uploader_id=owner.user.id,
        filename="synthetic-cv.pdf",
        content_type="application/pdf",
        data=_pdf_bytes(),
    )
    stored = storage_root / str(owner.org.id) / str(document.id) / document.internal_name

    delete_document(
        db,
        organization_id=owner.org.id,
        document_id=document.id,
        actor_id=owner.user.id,
    )

    assert not stored.exists()
    assert db.scalars(select(Document)).all() == []
    events = list_resource_events(db, owner.org.id, "document", document.id)
    assert [event.action for event in events] == ["document.uploaded", "document.deleted"]
