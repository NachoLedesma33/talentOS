from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import email_validator
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

# Registrar tablas al importar, como en el resto de tests de API.
import app.audit.models  # noqa: F401  # registra audit_log en Base.metadata
import app.candidates.models  # noqa: F401  # registra candidates en Base.metadata
import app.documents.models  # noqa: F401  # registra documents en Base.metadata
import app.identity.models  # noqa: F401  # registra identity en Base.metadata
from app.audit.models import AuditLog
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.documents import storage as storage_module
from app.documents import tokens
from app.documents.models import Document
from app.documents.validation import ALLOWED_MIME, MAX_SIZE_BYTES
from app.main import app

_URL = "/api/v1/documents"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-documents-api@example.test"
_OWNER_B = "owner-b-documents-api@example.test"
_RECRUITER = "recruiter-documents-api@example.test"
_VIEWER = "viewer-documents-api@example.test"


@pytest.fixture(autouse=True)
def _allow_synthetic_test_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_validator, "TEST_ENVIRONMENT", True)


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Storage privado aislado por test; nunca se escribe en var/ real."""
    root = tmp_path / "var" / "documents"
    monkeypatch.setattr(storage_module, "_base_dir", lambda: root)
    return root


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


@pytest.fixture
def seeded(client: TestClient) -> dict[str, str]:
    """Dos tenants sintéticos; deja sesión iniciada como recruiter del tenant A."""
    _register(client, _OWNER_A, "Synthetic Owner A")
    _register(client, _RECRUITER, "Synthetic Recruiter")
    _register(client, _VIEWER, "Synthetic Viewer")
    _register(client, _OWNER_B, "Synthetic Owner B")

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Org A", "documents-api-org-a")
    headers_a = _headers(org_a)
    for email, role in ((_RECRUITER, "recruiter"), (_VIEWER, "viewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers=headers_a,
        )
        assert response.status_code == 201, response.text
    candidate_a = _create_candidate(client, headers_a, "candidate-a-documents@example.test")

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Org B", "documents-api-org-b")
    candidate_b = _create_candidate(
        client, _headers(org_b), "candidate-b-documents@example.test"
    )

    _login(client, _RECRUITER)
    return {
        "org_a": org_a,
        "org_b": org_b,
        "candidate_a": candidate_a,
        "candidate_b": candidate_b,
    }


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
    assert _COOKIE in client.cookies


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORGS_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


def _create_candidate(client: TestClient, headers: dict[str, str], email: str) -> str:
    response = client.post(
        "/api/v1/candidates",
        json={"name": "Synthetic Candidate", "email": email},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document><w:body>Synthetic</w:body></w:document>")
        archive.writestr("[Content_Types].xml", "<Types/>")
    return buffer.getvalue()


def _upload(
    client: TestClient,
    *,
    org_id: str,
    candidate_id: str,
    filename: str = "synthetic-cv.pdf",
    content_type: str = "application/pdf",
    data: bytes | None = None,
    via_query: bool = False,
) -> Response:
    files = {"file": (filename, data if data is not None else _pdf_bytes(), content_type)}
    kwargs: dict[str, object] = {"files": files, "headers": _headers(org_id)}
    if via_query:
        kwargs["params"] = {"candidate_id": candidate_id}
    else:
        kwargs["data"] = {"candidate_id": candidate_id}
    return client.post(f"{_URL}/upload", **kwargs)


def _download_url(client: TestClient, *, org_id: str, document_id: str) -> str:
    response = client.get(
        f"{_URL}/{document_id}/download", headers=_headers(org_id)
    )
    assert response.status_code == 200, response.text
    return str(response.json()["url"])


def test_upload_accepts_synthetic_pdf_and_docx_with_public_metadata_only(
    client: TestClient, seeded: dict[str, str]
) -> None:
    org_id = seeded["org_a"]
    candidate_id = seeded["candidate_a"]
    pdf_data = _pdf_bytes()
    docx_data = _docx_bytes()

    pdf = _upload(client, org_id=org_id, candidate_id=candidate_id, data=pdf_data)
    docx = _upload(
        client,
        org_id=org_id,
        candidate_id=candidate_id,
        filename="synthetic-cv.docx",
        content_type=ALLOWED_MIME[".docx"],
        data=docx_data,
        via_query=True,
    )

    assert pdf.status_code == 201, pdf.text
    assert docx.status_code == 201, docx.text
    body = pdf.json()
    assert set(body) == {
        "id",
        "candidate_id",
        "original_filename",
        "content_type",
        "extension",
        "size_bytes",
        "checksum_sha256",
        "status",
        "page_count",
        "created_at",
    }
    assert body["candidate_id"] == candidate_id
    assert body["original_filename"] == "synthetic-cv.pdf"
    assert body["extension"] == ".pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(pdf_data)
    assert body["checksum_sha256"] == hashlib.sha256(pdf_data).hexdigest()
    assert body["status"] == "uploaded"
    assert body["page_count"] is None
    assert docx.json()["extension"] == ".docx"


@pytest.mark.parametrize(
    ("filename", "content_type", "data", "code"),
    [
        ("synthetic-cv.txt", "application/pdf", None, "invalid_extension"),
        ("synthetic-cv.pdf", "text/plain", None, "invalid_mime"),
        ("synthetic-cv.pdf", "application/pdf", b"not a pdf", "invalid_signature"),
        (
            "synthetic-cv.docx",
            ALLOWED_MIME[".docx"],
            None,
            "invalid_signature",
        ),
    ],
)
def test_fake_extension_mime_and_signature_return_400_stable_code(
    client: TestClient,
    seeded: dict[str, str],
    filename: str,
    content_type: str,
    data: bytes | None,
    code: str,
) -> None:
    response = _upload(
        client,
        org_id=seeded["org_a"],
        candidate_id=seeded["candidate_a"],
        filename=filename,
        content_type=content_type,
        data=data,
    )

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert "synthetic-cv" not in str(error)
    assert "not a pdf" not in str(error)


def test_oversized_file_is_rejected_with_stable_code(
    client: TestClient, seeded: dict[str, str]
) -> None:
    response = _upload(
        client,
        org_id=seeded["org_a"],
        candidate_id=seeded["candidate_a"],
        data=b"%PDF-" + b"0" * MAX_SIZE_BYTES,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "too_large"


def test_missing_or_invalid_candidate_id_returns_400(
    client: TestClient, seeded: dict[str, str]
) -> None:
    files = {"file": ("synthetic-cv.pdf", _pdf_bytes(), "application/pdf")}
    headers = _headers(seeded["org_a"])

    missing = client.post(f"{_URL}/upload", files=files, headers=headers)
    invalid = client.post(
        f"{_URL}/upload",
        files={"file": ("synthetic-cv.pdf", _pdf_bytes(), "application/pdf")},
        data={"candidate_id": "not-a-uuid"},
        headers=headers,
    )

    assert missing.status_code == 400
    assert invalid.status_code == 400
    assert missing.json()["error"]["code"] == "invalid_candidate_id"
    assert invalid.json()["error"]["code"] == "invalid_candidate_id"


def test_list_get_pagination_filter_and_cross_tenant_404(
    client: TestClient, seeded: dict[str, str]
) -> None:
    org_a = seeded["org_a"]
    org_b = seeded["org_b"]
    first = _upload(client, org_id=org_a, candidate_id=seeded["candidate_a"])
    second = _upload(client, org_id=org_a, candidate_id=seeded["candidate_a"])
    _login(client, _OWNER_B)
    foreign = _upload(client, org_id=org_b, candidate_id=seeded["candidate_b"])
    _login(client, _RECRUITER)
    assert first.status_code == second.status_code == foreign.status_code == 201
    first_id = first.json()["id"]
    foreign_id = foreign.json()["id"]

    page_one = client.get(
        _URL, headers=_headers(org_a), params={"limit": 1, "offset": 0}
    )
    page_two = client.get(
        _URL, headers=_headers(org_a), params={"limit": 1, "offset": 1}
    )
    filtered = client.get(
        _URL, headers=_headers(org_a), params={"candidate_id": seeded["candidate_a"]}
    )
    assert page_one.status_code == page_two.status_code == filtered.status_code == 200
    assert page_one.json()["total"] == 2
    assert page_one.json()["limit"] == 1
    assert page_one.json()["offset"] == 0
    assert len(page_one.json()["items"]) == 1
    assert len(page_two.json()["items"]) == 1
    assert page_one.json()["items"][0]["id"] != page_two.json()["items"][0]["id"]
    assert filtered.json()["total"] == 2

    own = client.get(f"{_URL}/{first_id}", headers=_headers(org_a))
    assert own.status_code == 200
    assert own.json()["id"] == first_id
    assert (
        client.get(f"{_URL}/{foreign_id}", headers=_headers(org_a)).status_code == 404
    )
    # Sin membresía en B, el header ajeno se rechaza con 403 antes de tocar la fila.
    assert client.get(f"{_URL}/{first_id}", headers=_headers(org_b)).status_code == 403
    _login(client, _OWNER_B)
    assert client.get(f"{_URL}/{first_id}", headers=_headers(org_b)).status_code == 404
    _login(client, _RECRUITER)

    foreign_candidate_upload = _upload(
        client, org_id=org_a, candidate_id=seeded["candidate_b"]
    )
    assert foreign_candidate_upload.status_code == 404


def test_download_url_expires_and_tampered_token_is_forbidden(
    client: TestClient, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = seeded["org_a"]
    doc = _upload(client, org_id=org_id, candidate_id=seeded["candidate_a"])
    assert doc.status_code == 201
    url = _download_url(client, org_id=org_id, document_id=doc.json()["id"])
    assert url.startswith("/api/v1/documents/files/")

    tampered = url[:-1] + ("A" if url[-1] != "A" else "B")
    assert client.get(tampered, headers=_headers(org_id)).status_code == 403

    monkeypatch.setattr(
        tokens, "_now", lambda: datetime.now(UTC) + timedelta(seconds=61)
    )
    assert client.get(url, headers=_headers(org_id)).status_code == 403


def test_file_endpoint_serves_attachment_only_to_token_organization(
    client: TestClient, seeded: dict[str, str], storage_root: Path
) -> None:
    org_a = seeded["org_a"]
    org_b = seeded["org_b"]
    pdf_data = _pdf_bytes()
    doc = _upload(
        client, org_id=org_a, candidate_id=seeded["candidate_a"], data=pdf_data
    )
    assert doc.status_code == 201
    url = _download_url(client, org_id=org_a, document_id=doc.json()["id"])

    own = client.get(url, headers=_headers(org_a))
    assert own.status_code == 200
    assert own.content == pdf_data
    assert own.headers["content-type"] == "application/pdf"
    assert "attachment" in own.headers["content-disposition"]
    assert not any(
        "path" in key.lower() or "storage" in key.lower() for key in own.headers
    )
    assert str(storage_root) not in str(own.headers)

    _login(client, _OWNER_B)
    foreign = client.get(url, headers=_headers(org_b))
    assert foreign.status_code == 403

    _login(client, _VIEWER)
    wrong_header = client.get(url, headers=_headers(org_b))
    assert wrong_header.status_code == 403


def test_delete_removes_private_file_and_row(
    client: TestClient, seeded: dict[str, str], storage_root: Path, db: DBSession
) -> None:
    org_id = seeded["org_a"]
    doc = _upload(client, org_id=org_id, candidate_id=seeded["candidate_a"])
    assert doc.status_code == 201
    document_id = doc.json()["id"]
    document_dir = storage_root / org_id / document_id
    assert any(document_dir.iterdir())

    deleted = client.delete(f"{_URL}/{document_id}", headers=_headers(org_id))

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert not any(document_dir.iterdir())
    assert db.get(Document, UUID(document_id)) is None
    assert client.get(f"{_URL}/{document_id}", headers=_headers(org_id)).status_code == 404


def test_viewer_can_read_but_cannot_upload_or_delete(
    client: TestClient, seeded: dict[str, str]
) -> None:
    org_id = seeded["org_a"]
    doc = _upload(client, org_id=org_id, candidate_id=seeded["candidate_a"])
    assert doc.status_code == 201
    document_id = doc.json()["id"]
    _login(client, _VIEWER)

    listing = client.get(_URL, headers=_headers(org_id))
    detail = client.get(f"{_URL}/{document_id}", headers=_headers(org_id))
    download = client.get(f"{_URL}/{document_id}/download", headers=_headers(org_id))
    upload = _upload(client, org_id=org_id, candidate_id=seeded["candidate_a"])
    delete = client.delete(f"{_URL}/{document_id}", headers=_headers(org_id))

    assert listing.status_code == detail.status_code == download.status_code == 200
    assert upload.status_code == 403
    assert delete.status_code == 403


def test_requests_without_session_cookie_are_unauthorized(
    client: TestClient, seeded: dict[str, str]
) -> None:
    doc = _upload(client, org_id=seeded["org_a"], candidate_id=seeded["candidate_a"])
    assert doc.status_code == 201
    document_id = doc.json()["id"]
    client.cookies.clear()

    assert client.get(_URL, headers=_headers(seeded["org_a"])).status_code == 401
    assert (
        client.get(f"{_URL}/{document_id}", headers=_headers(seeded["org_a"])).status_code
        == 401
    )
    assert (
        client.get(
            f"{_URL}/{document_id}/download", headers=_headers(seeded["org_a"])
        ).status_code
        == 401
    )
    assert (
        client.get(
            f"{_URL}/files/{uuid4()}", headers=_headers(seeded["org_a"])
        ).status_code
        == 401
    )
    assert (
        _upload(client, org_id=seeded["org_a"], candidate_id=seeded["candidate_a"]).status_code
        == 401
    )
    assert (
        client.delete(f"{_URL}/{document_id}", headers=_headers(seeded["org_a"])).status_code
        == 401
    )


def test_audit_records_download_without_filename_or_storage_path(
    client: TestClient, seeded: dict[str, str], storage_root: Path, db: DBSession
) -> None:
    org_id = seeded["org_a"]
    doc = _upload(client, org_id=org_id, candidate_id=seeded["candidate_a"])
    assert doc.status_code == 201
    document_id = doc.json()["id"]
    url = _download_url(client, org_id=org_id, document_id=document_id)
    assert client.get(url, headers=_headers(org_id)).status_code == 200
    assert client.delete(f"{_URL}/{document_id}", headers=_headers(org_id)).status_code == 204

    entries = db.execute(
        select(AuditLog).where(AuditLog.organization_id == UUID(org_id))
    ).scalars().all()
    actions = {entry.action for entry in entries}
    assert {"document.uploaded", "document.downloaded", "document.deleted"} <= actions

    columns = set(AuditLog.__table__.columns.keys())
    assert columns == {
        "id",
        "organization_id",
        "actor_id",
        "action",
        "resource_type",
        "resource_id",
        "timestamp",
    }
    values = " ".join(
        str(getattr(entry, name)) for entry in entries for name in sorted(columns)
    )
    assert "synthetic-cv.pdf" not in values
    assert str(storage_root) not in values
    assert "\\" not in values
    assert "/var/" not in values
    assert "document.downloaded" in values
