from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import email_validator
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

# Registrar tablas al importar, igual que los tests de API existentes.
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
from app.audit.models import AuditLog
from app.candidates.models import Candidate
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.documents import storage as storage_module
from app.documents import tasks as tasks_module
from app.documents.extraction import (
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_PROVIDER,
)
from app.documents.models import Document, DocumentExtraction, DocumentStatus, ExtractionStatus
from app.documents.repositories import get_extraction_for_worker
from app.documents.service import (
    DocumentsDomainError,
    create_document,
    start_extraction,
)
from app.identity.models import Membership, MembershipRole, Organization, User
from app.main import app

_CV_MARKER = "SyntheticCVSecret"
_URL = "/api/v1/documents"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-extract@example.test"
_OWNER_B = "owner-b-extract@example.test"
_ADMIN = "admin-extract@example.test"
_RECRUITER = "recruiter-extract@example.test"
_VIEWER = "viewer-extract@example.test"


@dataclass(frozen=True)
class _Tenant:
    org: Organization
    user: User
    candidate: Candidate


@dataclass(frozen=True)
class _Environment:
    owner: _Tenant
    outsider: _Tenant
    viewer: User


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
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
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "var" / "documents"
    monkeypatch.setattr(storage_module, "_base_dir", lambda: root)
    return root


@pytest.fixture
def task_sessions(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """El worker abre su propia sesión, pero contra la SQLite aislada del test."""
    monkeypatch.setattr(
        tasks_module, "SessionLocal", lambda: DBSession(engine, expire_on_commit=False)
    )


@pytest.fixture
def tenants(db: DBSession) -> _Environment:
    org_a = Organization(name="Org A", slug="tasks-org-a")
    org_b = Organization(name="Org B", slug="tasks-org-b")
    owner = User(email=_OWNER_A, password_hash="synthetic-hash", name="Synthetic Owner")
    outsider = User(
        email=_OWNER_B, password_hash="synthetic-hash", name="Synthetic Outsider"
    )
    viewer = User(email=_VIEWER, password_hash="synthetic-hash", name="Synthetic Viewer")
    db.add_all([org_a, org_b, owner, outsider, viewer])
    db.flush()
    db.add_all(
        [
            Membership(organization_id=org_a.id, user_id=owner.id, role=MembershipRole.OWNER),
            Membership(organization_id=org_b.id, user_id=outsider.id, role=MembershipRole.OWNER),
            Membership(organization_id=org_a.id, user_id=viewer.id, role=MembershipRole.VIEWER),
        ]
    )
    candidate_a = Candidate(
        organization_id=org_a.id, name="Synthetic A", email="candidate-a-tasks@example.test"
    )
    candidate_b = Candidate(
        organization_id=org_b.id, name="Synthetic B", email="candidate-b-tasks@example.test"
    )
    db.add_all([candidate_a, candidate_b])
    db.commit()
    return _Environment(
        owner=_Tenant(org_a, owner, candidate_a),
        outsider=_Tenant(org_b, outsider, candidate_b),
        viewer=viewer,
    )


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[DBSession]:
        with DBSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def api(client: TestClient) -> dict[str, str]:
    """Dos tenants sintéticos con owner, admin, recruiter y viewer en el tenant A."""
    for email, name in (
        (_OWNER_A, "Synthetic Owner"),
        (_OWNER_B, "Synthetic Owner B"),
        (_ADMIN, "Synthetic Admin"),
        (_RECRUITER, "Synthetic Recruiter"),
        (_VIEWER, "Synthetic Viewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Org A", "api-extract-org-a")
    for email, role in (
        (_ADMIN, "admin"),
        (_RECRUITER, "recruiter"),
        (_VIEWER, "viewer"),
    ):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers=_headers(org_a),
        )
        assert response.status_code == 201, response.text
    candidate_a = _create_candidate(client, org_a, "candidate-a-api@example.test")

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Org B", "api-extract-org-b")
    candidate_b = _create_candidate(client, org_b, "candidate-b-api@example.test")

    _login(client, _RECRUITER)
    return {
        "org_a": org_a,
        "org_b": org_b,
        "candidate_a": candidate_a,
        "candidate_b": candidate_b,
    }


def _pdf_bytes(marker: str = "Synthetic alpha") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 180 Td ({marker}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _corrupt_pdf_bytes() -> bytes:
    # Firma válida para el upload; el extractor debe rechazar el contenido.
    return f"%PDF-1.4\n{_CV_MARKER}\n".encode("ascii")


def _make_document(
    db: DBSession, tenant: _Tenant, *, data: bytes | None = None
) -> Document:
    return create_document(
        db,
        organization_id=tenant.org.id,
        candidate_id=tenant.candidate.id,
        uploader_id=tenant.user.id,
        filename="synthetic-cv.pdf",
        content_type="application/pdf",
        data=data if data is not None else _pdf_bytes(),
    )


def _register(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "name": name},
    )
    assert response.status_code == 201, response.text


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200, response.text
    assert _COOKIE in client.cookies


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORGS_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


def _create_candidate(client: TestClient, org_id: str, email: str) -> str:
    response = client.post(
        "/api/v1/candidates",
        json={"name": "Synthetic Candidate", "email": email},
        headers=_headers(org_id),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _upload(client: TestClient, *, org_id: str, candidate_id: str) -> str:
    response = client.post(
        f"{_URL}/upload",
        files={"file": ("synthetic-cv.pdf", _pdf_bytes(), "application/pdf")},
        data={"candidate_id": candidate_id},
        headers=_headers(org_id),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_foreign_organization_aborts_before_reading_storage(
    db: DBSession,
    storage_root: Path,
    task_sessions: None,
    tenants: _Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _make_document(db, tenants.owner)
    reads: list[object] = []

    def forbidden_read(**_kwargs: object) -> bytes:
        reads.append(True)
        raise AssertionError("El worker no debe leer storage de otra organización.")

    monkeypatch.setattr(storage_module, "read_document", forbidden_read)

    tasks_module.extract_document(str(document.id), str(tenants.outsider.org.id))

    assert reads == []
    assert db.get(Document, document.id).status is DocumentStatus.UPLOADED
    assert db.scalars(select(DocumentExtraction)).all() == []


def test_task_persists_completed_extraction_and_processed_document(
    db: DBSession,
    storage_root: Path,
    task_sessions: None,
    tenants: _Environment,
) -> None:
    document = _make_document(db, tenants.owner)

    tasks_module.extract_document(str(document.id), str(tenants.owner.org.id))
    db.expire_all()

    extraction = get_extraction_for_worker(
        db, document.id, EXTRACTION_PROVIDER, EXTRACTION_PROMPT_VERSION
    )
    assert extraction is not None
    assert extraction.status is ExtractionStatus.COMPLETED
    assert extraction.provider == EXTRACTION_PROVIDER
    assert extraction.prompt_version == EXTRACTION_PROMPT_VERSION
    assert extraction.pages[0]["page"] == 1
    assert "Synthetic alpha" in str(extraction.pages[0]["text"])
    stored = db.get(Document, document.id)
    assert stored.status is DocumentStatus.PROCESSED
    assert stored.page_count == len(extraction.pages)
    assert stored.error_code is None


def test_task_failure_persists_stable_code_without_cv_in_logs(
    db: DBSession,
    storage_root: Path,
    task_sessions: None,
    tenants: _Environment,
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = _make_document(db, tenants.owner, data=_corrupt_pdf_bytes())
    caplog.set_level(logging.DEBUG)

    tasks_module.extract_document(str(document.id), str(tenants.owner.org.id))
    db.expire_all()

    extraction = get_extraction_for_worker(
        db, document.id, EXTRACTION_PROVIDER, EXTRACTION_PROMPT_VERSION
    )
    assert extraction is not None
    assert extraction.status is ExtractionStatus.FAILED
    assert extraction.error_code == "corrupt_document"
    assert extraction.pages == []
    stored = db.get(Document, document.id)
    assert stored.status is DocumentStatus.FAILED
    assert stored.error_code == "corrupt_document"
    assert _CV_MARKER not in caplog.text
    assert "Traceback" not in caplog.text


def test_task_does_not_duplicate_extraction_for_same_key(
    db: DBSession,
    storage_root: Path,
    task_sessions: None,
    tenants: _Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _make_document(db, tenants.owner)
    original_read = storage_module.read_document
    reads: list[object] = []

    def counting_read(**kwargs: object) -> bytes:
        reads.append(True)
        return original_read(**kwargs)  # type: ignore[return-value]

    monkeypatch.setattr(storage_module, "read_document", counting_read)

    tasks_module.extract_document(str(document.id), str(tenants.owner.org.id))
    tasks_module.extract_document(str(document.id), str(tenants.owner.org.id))

    assert len(reads) == 1
    assert len(db.scalars(select(DocumentExtraction)).all()) == 1


def test_start_extraction_queues_ids_and_audits(
    db: DBSession,
    storage_root: Path,
    tenants: _Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _make_document(db, tenants.owner)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        tasks_module.extract_document,
        "delay",
        lambda *args: calls.append(tuple(str(arg) for arg in args)),
    )

    result = start_extraction(
        db, tenants.owner.org.id, document.id, tenants.owner.user.id
    )

    assert calls == [(str(document.id), str(tenants.owner.org.id))]
    assert result["document_id"] == str(document.id)
    assert result["status"] == "processing"
    assert result["provider"] == EXTRACTION_PROVIDER
    assert result["prompt_version"] == EXTRACTION_PROMPT_VERSION
    assert db.get(Document, document.id).status is DocumentStatus.PROCESSING
    extraction = get_extraction_for_worker(
        db, document.id, EXTRACTION_PROVIDER, EXTRACTION_PROMPT_VERSION
    )
    assert extraction is not None
    assert extraction.status is ExtractionStatus.PENDING
    actions = [
        event.action
        for event in db.scalars(select(AuditLog).where(AuditLog.resource_id == document.id)).all()
    ]
    assert {"document.uploaded", "document.extraction_requested"} <= set(actions)


def test_start_extraction_rejects_foreign_actor_viewer_and_invalid_status(
    db: DBSession, storage_root: Path, tenants: _Environment
) -> None:
    document = _make_document(db, tenants.owner)

    with pytest.raises(DocumentsDomainError) as foreign:
        start_extraction(db, tenants.owner.org.id, document.id, tenants.outsider.user.id)
    assert foreign.value.code == "forbidden"

    with pytest.raises(DocumentsDomainError) as viewer:
        start_extraction(db, tenants.owner.org.id, document.id, tenants.viewer.id)
    assert viewer.value.code == "forbidden"

    document.status = DocumentStatus.PROCESSED
    db.commit()
    with pytest.raises(DocumentsDomainError) as invalid:
        start_extraction(db, tenants.owner.org.id, document.id, tenants.owner.user.id)
    assert invalid.value.code == "invalid_status"
    assert db.get(Document, document.id).status is DocumentStatus.PROCESSED


def test_broker_failure_leaves_failed_document_without_exception_text(
    db: DBSession,
    storage_root: Path,
    tenants: _Environment,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = _make_document(db, tenants.owner)
    secret_like_message = "synthetic-broker-secret-token"

    def fail_delay(*_args: object) -> None:
        raise RuntimeError(secret_like_message)

    monkeypatch.setattr(tasks_module.extract_document, "delay", fail_delay)
    caplog.set_level(logging.DEBUG)

    result = start_extraction(db, tenants.owner.org.id, document.id, tenants.owner.user.id)

    assert result["status"] == "failed"
    stored = db.get(Document, document.id)
    assert stored.status is DocumentStatus.FAILED
    assert stored.error_code == "broker_unavailable"
    extraction = get_extraction_for_worker(
        db, document.id, EXTRACTION_PROVIDER, EXTRACTION_PROMPT_VERSION
    )
    assert extraction is not None
    assert extraction.status is ExtractionStatus.FAILED
    assert extraction.error_code == "broker_unavailable"
    assert secret_like_message not in caplog.text
    assert "Traceback" not in caplog.text


def test_extract_endpoint_returns_202_and_cross_tenant_returns_404(
    client: TestClient,
    api: dict[str, str],
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        tasks_module.extract_document,
        "delay",
        lambda *args: calls.append(tuple(str(arg) for arg in args)),
    )
    document_id = _upload(client, org_id=api["org_a"], candidate_id=api["candidate_a"])

    response = client.post(
        f"{_URL}/{document_id}/extract", headers=_headers(api["org_a"])
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["document_id"] == document_id
    assert body["status"] == "processing"
    assert body["provider"] == EXTRACTION_PROVIDER
    assert body["prompt_version"] == EXTRACTION_PROMPT_VERSION
    assert calls == [(document_id, api["org_a"])]
    current = client.get(f"{_URL}/{document_id}", headers=_headers(api["org_a"]))
    assert current.status_code == 200
    assert current.json()["status"] == "processing"

    _login(client, _OWNER_B)
    foreign = client.post(
        f"{_URL}/{document_id}/extract", headers=_headers(api["org_b"])
    )
    assert foreign.status_code == 404
    assert calls == [(document_id, api["org_a"])]


def test_extract_endpoint_requires_write_role_and_session(
    client: TestClient,
    api: dict[str, str],
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(tasks_module.extract_document, "delay", lambda *args: calls.append(args))

    _login(client, _OWNER_A)
    viewer_doc = _upload(client, org_id=api["org_a"], candidate_id=api["candidate_a"])

    _login(client, _VIEWER)
    assert (
        client.post(
            f"{_URL}/{viewer_doc}/extract", headers=_headers(api["org_a"])
        ).status_code
        == 403
    )
    assert calls == []

    for email in (_RECRUITER, _ADMIN, _OWNER_A):
        _login(client, email)
        document_id = _upload(client, org_id=api["org_a"], candidate_id=api["candidate_a"])
        response = client.post(
            f"{_URL}/{document_id}/extract", headers=_headers(api["org_a"])
        )
        assert response.status_code == 202, response.text

    client.cookies.clear()
    assert (
        client.post(
            f"{_URL}/{viewer_doc}/extract", headers=_headers(api["org_a"])
        ).status_code
        == 401
    )
