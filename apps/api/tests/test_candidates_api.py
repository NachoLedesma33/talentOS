from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import email_validator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

# Registrar tablas al importar: `test_auth` recarga `app.db.base` al terminar y
# los modelos importados después quedarían en una metadata distinta de `Base`.
import app.audit.models  # noqa: F401  # registra audit_log en Base.metadata
import app.candidates.models  # noqa: F401  # registra candidates en Base.metadata
import app.identity.models  # noqa: F401  # registra identity en Base.metadata
from app.audit.models import AuditLog
from app.candidates import service as candidates_service
from app.candidates.models import CandidateNote
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_CANDIDATES_URL = "/api/v1/candidates"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"

_OWNER_A = "owner-candidates@example.test"
_OWNER_B = "owner-b-candidates@example.test"
_RECRUITER = "recruiter-candidates@example.test"
_REVIEWER = "reviewer-candidates@example.test"
_VIEWER = "viewer-candidates@example.test"


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


@pytest.fixture
def seeded(client: TestClient) -> dict[str, str]:
    """Dos tenants sintéticos con roles reales; deja sesión iniciada como recruiter."""
    _register(client, _OWNER_A, "Synthetic Owner A")
    recruiter_id = _register(client, _RECRUITER, "Synthetic Recruiter")
    reviewer_id = _register(client, _REVIEWER, "Synthetic Reviewer")
    viewer_id = _register(client, _VIEWER, "Synthetic Viewer")
    _register(client, _OWNER_B, "Synthetic Owner B")

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Org A", "candidates-org-a")
    headers_a = _org_headers(org_a)
    for email, role in ((_RECRUITER, "recruiter"), (_REVIEWER, "reviewer"), (_VIEWER, "viewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers=headers_a,
        )
        assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Org B", "candidates-org-b")
    _login(client, _RECRUITER)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "recruiter_id": recruiter_id,
        "reviewer_id": reviewer_id,
        "viewer_id": viewer_id,
    }


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


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORGS_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _org_headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


def _candidate_payload(
    name: str = "Synthetic Candidate",
    email: str = "candidate-candidates@example.test",
    location: str | None = "Synthetic City",
) -> dict[str, object]:
    return {"name": name, "email": email, "location": location}


def _create_candidate(
    client: TestClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    response = client.post(
        _CANDIDATES_URL, json={**_candidate_payload(), **overrides}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_list_search_filter_and_paginate_candidates(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    first = _create_candidate(
        client, headers, name="Synthetic Ada", email="ada.candidates@example.test"
    )
    second = _create_candidate(
        client, headers, name="Synthetic Grace", email="grace.candidates@example.test"
    )
    third = _create_candidate(
        client, headers, name="Other Person", email="other.candidates@example.test"
    )

    page_one = client.get(_CANDIDATES_URL, headers=headers, params={"limit": 2, "offset": 0})
    page_two = client.get(_CANDIDATES_URL, headers=headers, params={"limit": 2, "offset": 2})
    by_name = client.get(_CANDIDATES_URL, headers=headers, params={"q": " SYNTHETIC "})
    by_email = client.get(_CANDIDATES_URL, headers=headers, params={"q": "GRACE.CANDIDATES@"})
    updated = client.patch(
        f"{_CANDIDATES_URL}/{second['id']}",
        json={"profile_status": "review"},
        headers=headers,
    )
    by_status = client.get(_CANDIDATES_URL, headers=headers, params={"status": "review"})

    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert page_one.json() == {
        "items": page_one.json()["items"],
        "total": 3,
        "limit": 2,
        "offset": 0,
    }
    page_ids = [item["id"] for item in page_one.json()["items"]]
    page_ids += [item["id"] for item in page_two.json()["items"]]
    assert set(page_ids) == {first["id"], second["id"], third["id"]}
    assert page_two.json()["total"] == 3
    assert page_two.json()["offset"] == 2

    assert by_name.status_code == 200
    assert by_name.json()["total"] == 2
    assert {item["id"] for item in by_name.json()["items"]} == {first["id"], second["id"]}
    assert by_email.json()["total"] == 1
    assert by_email.json()["items"][0]["id"] == second["id"]

    assert updated.status_code == 200
    assert updated.json()["profile_status"] == "review"
    assert by_status.status_code == 200
    assert by_status.json()["total"] == 1
    assert by_status.json()["items"][0]["id"] == second["id"]

    assert first["profile_status"] == "draft"
    assert "organization_id" not in first
    assert not _PROTECTED_FIELDS & set(first)


_PROTECTED_FIELDS = frozenset(
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


def test_reader_roles_read_candidates_but_viewer_cannot_read_notes(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    candidate = _create_candidate(client, headers)

    _login(client, _VIEWER)
    listing = client.get(_CANDIDATES_URL, headers=headers)
    detail = client.get(f"{_CANDIDATES_URL}/{candidate['id']}", headers=headers)
    viewer_notes = client.get(f"{_CANDIDATES_URL}/{candidate['id']}/notes", headers=headers)
    viewer_patch = client.patch(
        f"{_CANDIDATES_URL}/{candidate['id']}", json={"name": "Tampered"}, headers=headers
    )
    viewer_note = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/notes",
        json={"body": "Synthetic note"},
        headers=headers,
    )

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["name"] == "Synthetic Candidate"
    assert viewer_notes.status_code == 403
    assert viewer_patch.status_code == 403
    assert viewer_note.status_code == 403
    assert viewer_notes.json()["error"]["code"] == "forbidden"

    _login(client, _REVIEWER)
    reviewer_notes = client.get(f"{_CANDIDATES_URL}/{candidate['id']}/notes", headers=headers)
    reviewer_note = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/notes",
        json={"body": "Synthetic note"},
        headers=headers,
    )
    assert reviewer_notes.status_code == 200
    assert reviewer_notes.json() == []
    assert reviewer_note.status_code == 403


def test_cross_tenant_candidate_and_notes_are_not_revealed(
    client: TestClient, seeded: dict[str, str]
) -> None:
    owner_b_headers = _org_headers(seeded["org_b"])
    _login(client, _OWNER_B)
    foreign = _create_candidate(client, owner_b_headers, name="Foreign Candidate")
    _login(client, _RECRUITER)
    headers = _org_headers(seeded["org_a"])

    detail = client.get(f"{_CANDIDATES_URL}/{foreign['id']}", headers=headers)
    patch = client.patch(
        f"{_CANDIDATES_URL}/{foreign['id']}", json={"name": "Tampered"}, headers=headers
    )
    notes = client.get(f"{_CANDIDATES_URL}/{foreign['id']}/notes", headers=headers)
    add_note = client.post(
        f"{_CANDIDATES_URL}/{foreign['id']}/notes",
        json={"body": "Tampered note"},
        headers=headers,
    )
    activity = client.get(f"{_CANDIDATES_URL}/{foreign['id']}/activity", headers=headers)
    listing = client.get(_CANDIDATES_URL, headers=headers)

    for response in (detail, patch, notes, add_note, activity):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "not_found"
    assert listing.status_code == 200
    assert listing.json()["total"] == 0


def test_note_is_linked_to_author_and_events_are_auditable(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    headers = _org_headers(seeded["org_a"])
    candidate = _create_candidate(client, headers)
    candidate_id = UUID(str(candidate["id"]))
    organization_id = UUID(seeded["org_a"])
    actor_id = UUID(seeded["recruiter_id"])

    updated = client.patch(
        f"{_CANDIDATES_URL}/{candidate['id']}",
        json={"name": "Synthetic Candidate Updated"},
        headers=headers,
    )
    note = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/notes",
        json={"body": "Synthetic internal note"},
        headers=headers,
    )
    listed = client.get(f"{_CANDIDATES_URL}/{candidate['id']}/notes", headers=headers)
    activity = client.get(f"{_CANDIDATES_URL}/{candidate['id']}/activity", headers=headers)

    assert updated.status_code == 200
    assert note.status_code == 201, note.text
    assert note.json()["candidate_id"] == candidate["id"]
    assert note.json()["author_id"] == seeded["recruiter_id"]
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [note.json()["id"]]

    note_id = UUID(str(note.json()["id"]))
    stored = db.scalar(select(CandidateNote).where(CandidateNote.id == note_id))
    assert stored is not None
    assert stored.candidate_id == candidate_id
    assert stored.author_id == actor_id

    assert activity.status_code == 200
    assert {entry["action"] for entry in activity.json()} == {
        "candidate.created",
        "candidate.updated",
        "note.added",
    }
    events = db.scalars(
        select(AuditLog).where(
            AuditLog.organization_id == organization_id,
            AuditLog.action.in_({"candidate.created", "candidate.updated", "note.added"}),
        )
    ).all()
    assert len(events) == 3
    for event in events:
        assert event.actor_id == actor_id
        assert event.resource_type == "candidate"
        assert event.resource_id == candidate_id
        assert "candidate-candidates@example.test" not in str(vars(event))


def test_email_is_normalized_and_note_body_is_validated(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    candidate = _create_candidate(
        client, headers, email="MiXeD.Candidate@Example.TEST"
    )
    assert candidate["email"] == "mixed.candidate@example.test"

    blank_note = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/notes", json={"body": "   "}, headers=headers
    )
    long_note = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/notes",
        json={"body": "x" * 2001},
        headers=headers,
    )
    valid_note = client.post(
        f"{_CANDIDATES_URL}/{candidate['id']}/notes",
        json={"body": "  Synthetic trimmed note  "},
        headers=headers,
    )
    updated = client.patch(
        f"{_CANDIDATES_URL}/{candidate['id']}",
        json={"email": " NEW.CANDIDATE@EXAMPLE.TEST "},
        headers=headers,
    )
    invalid_status = client.patch(
        f"{_CANDIDATES_URL}/{candidate['id']}",
        json={"profile_status": "unknown"},
        headers=headers,
    )

    assert blank_note.status_code == 422
    assert blank_note.json()["error"]["code"] == "validation_error"
    assert long_note.status_code == 422
    assert valid_note.status_code == 201
    assert valid_note.json()["body"] == "Synthetic trimmed note"
    assert updated.status_code == 200
    assert updated.json()["email"] == "new.candidate@example.test"
    assert invalid_status.status_code == 422


def test_service_rejects_blank_note_body(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    headers = _org_headers(seeded["org_a"])
    candidate = _create_candidate(client, headers, email="service.candidates@example.test")

    with pytest.raises(candidates_service.CandidateValidationError):
        candidates_service.add_note(
            db,
            organization_id=UUID(seeded["org_a"]),
            candidate_id=UUID(str(candidate["id"])),
            author_id=UUID(seeded["recruiter_id"]),
            body="   ",
        )

    assert db.scalars(select(CandidateNote)).all() == []


def test_requests_without_session_are_rejected_and_origin_is_checked(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    candidate = _create_candidate(client, headers)
    client.cookies.clear()

    listing = client.get(_CANDIDATES_URL, headers=headers)
    detail = client.get(f"{_CANDIDATES_URL}/{candidate['id']}", headers=headers)
    notes = client.get(f"{_CANDIDATES_URL}/{candidate['id']}/notes", headers=headers)
    activity = client.get(f"{_CANDIDATES_URL}/{candidate['id']}/activity", headers=headers)
    create = client.post(_CANDIDATES_URL, json=_candidate_payload(), headers=headers)

    for response in (listing, detail, notes, activity, create):
        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "unauthorized"

    _login(client, _RECRUITER)
    foreign_origin = client.post(
        _CANDIDATES_URL,
        json=_candidate_payload(email="origin.candidates@example.test"),
        headers={**headers, "Origin": "https://foreign.example"},
    )
    assert foreign_origin.status_code == 403
    assert foreign_origin.json()["error"]["code"] == "forbidden"


def test_export_is_tenant_scoped_limited_by_role_and_audited(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    headers = _org_headers(seeded["org_a"])
    own = _create_candidate(client, headers, email="export.candidates@example.test")
    client.post(
        f"{_CANDIDATES_URL}/{own['id']}/notes",
        json={"body": "Synthetic export note"},
        headers=headers,
    )

    _login(client, _OWNER_B)
    foreign = _create_candidate(
        client, _org_headers(seeded["org_b"]), email="foreign.export@example.test"
    )
    _login(client, _RECRUITER)

    response = client.get(f"{_CANDIDATES_URL}/export", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["organization_id"] == seeded["org_a"]
    assert [item["id"] for item in payload["candidates"]] == [own["id"]]
    assert payload["candidates"][0]["email"] == "export.candidates@example.test"
    assert [item["candidate_id"] for item in payload["notes"]] == [own["id"]]
    assert payload["notes"][0]["body"] == "Synthetic export note"
    assert payload["applications"] == []
    assert payload["documents"] == []
    assert foreign["id"] not in str(payload)
    assert "foreign.export@example.test" not in str(payload)

    event = db.scalar(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(seeded["org_a"]),
            AuditLog.action == "candidate.exported",
        )
    )
    assert event is not None
    assert event.actor_id == UUID(seeded["recruiter_id"])
    assert event.resource_type == "organization"
    assert event.resource_id == UUID(seeded["org_a"])

    _login(client, _VIEWER)
    denied = client.get(f"{_CANDIDATES_URL}/export", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
