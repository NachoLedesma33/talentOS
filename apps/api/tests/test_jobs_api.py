from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import email_validator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.audit.models  # noqa: F401  # registra audit_log en Base.metadata
import app.identity.models  # noqa: F401  # registra identity en Base.metadata
import app.jobs.models  # noqa: F401  # registra jobs en Base.metadata
from app.audit.models import AuditLog
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_JOBS_URL = "/api/v1/jobs"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"

_OWNER_A = "owner-jobs@example.test"
_RECRUITER = "recruiter-jobs@example.test"
_VIEWER = "viewer-jobs@example.test"
_OWNER_B = "owner-b-jobs@example.test"


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
    owner_a_id = _register(client, _OWNER_A, "Synthetic Owner A")
    recruiter_id = _register(client, _RECRUITER, "Synthetic Recruiter")
    viewer_id = _register(client, _VIEWER, "Synthetic Viewer")
    owner_b_id = _register(client, _OWNER_B, "Synthetic Owner B")

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Org A", "jobs-org-a")
    headers_a = _org_headers(org_a)
    for email, role in ((_RECRUITER, "recruiter"), (_VIEWER, "viewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers=headers_a,
        )
        assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Org B", "jobs-org-b")
    _login(client, _RECRUITER)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "owner_a_id": owner_a_id,
        "owner_b_id": owner_b_id,
        "recruiter_id": recruiter_id,
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


def _job_payload(owner_id: str, title: str = "Synthetic role") -> dict[str, object]:
    return {
        "title": title,
        "description": "Synthetic description",
        "modality": "remote",
        "location": "Synthetic City",
        "seniority": "mid",
        "owner_id": owner_id,
    }


def _create_job(
    client: TestClient, headers: dict[str, str], owner_id: str, title: str = "Synthetic role"
) -> dict[str, object]:
    response = client.post(_JOBS_URL, json=_job_payload(owner_id, title), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _requirement_payload() -> dict[str, object]:
    return {
        "category": "skill",
        "description": "Synthetic skill",
        "importance": "required",
        "expected_level": "mid",
        "acceptable_evidence": ["synthetic portfolio"],
        "weight": 0.5,
        "weight_justification": "Peso sintético explicado",
    }


def test_list_jobs_is_paginated_and_scoped_to_active_organization(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job_ids = [
        str(_create_job(client, headers, seeded["recruiter_id"], f"Synthetic role {index}")["id"])
        for index in range(3)
    ]

    first = client.get(_JOBS_URL, headers=headers, params={"limit": 2, "offset": 0})
    second = client.get(_JOBS_URL, headers=headers, params={"limit": 2, "offset": 2})
    foreign_header = client.get(_JOBS_URL, headers=_org_headers(seeded["org_b"]))
    _login(client, _OWNER_B)
    foreign_jobs = client.get(_JOBS_URL, headers=_org_headers(seeded["org_b"]))

    assert first.status_code == 200
    assert first.json() == {
        "items": first.json()["items"],
        "total": 3,
        "limit": 2,
        "offset": 0,
    }
    assert [item["id"] for item in first.json()["items"]] == job_ids[:2]
    assert [item["id"] for item in second.json()["items"]] == job_ids[2:]
    assert second.json()["total"] == 3
    assert foreign_header.status_code == 403
    assert foreign_jobs.status_code == 200
    assert foreign_jobs.json()["total"] == 0
    assert foreign_jobs.json()["items"] == []


def test_recruiter_creates_job_and_reader_roles_can_list(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    headers = _org_headers(seeded["org_a"])
    response = client.post(
        _JOBS_URL, json=_job_payload(seeded["recruiter_id"]), headers=headers
    )
    assert response.status_code == 201, response.text

    job = response.json()
    assert job["status"] == "draft"
    assert job["owner_id"] == seeded["recruiter_id"]
    assert "organization_id" not in job

    _login(client, _VIEWER)
    read = client.get(f"{_JOBS_URL}/{job['id']}", headers=headers)
    assert read.status_code == 200
    assert read.json()["title"] == "Synthetic role"

    audit = db.scalar(select(AuditLog).where(AuditLog.action == "job.created"))
    assert audit is not None
    assert audit.organization_id == UUID(seeded["org_a"])
    assert audit.actor_id == UUID(seeded["recruiter_id"])
    assert audit.resource_type == "job"
    assert audit.resource_id == UUID(str(job["id"]))


def test_viewer_cannot_create_job(client: TestClient, seeded: dict[str, str]) -> None:
    _login(client, _VIEWER)

    response = client.post(
        _JOBS_URL,
        json=_job_payload(seeded["viewer_id"]),
        headers=_org_headers(seeded["org_a"]),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_cross_tenant_job_and_requirement_are_not_revealed(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers_a = _org_headers(seeded["org_a"])
    headers_b = _org_headers(seeded["org_b"])
    _login(client, _OWNER_B)
    foreign_job = _create_job(client, headers_b, seeded["owner_b_id"], "Foreign role")
    foreign_requirement = client.post(
        f"{_JOBS_URL}/{foreign_job['id']}/requirements",
        json=_requirement_payload(),
        headers=headers_b,
    )
    assert foreign_requirement.status_code == 201, foreign_requirement.text
    _login(client, _RECRUITER)
    own_job = _create_job(client, headers_a, seeded["recruiter_id"])

    read = client.get(f"{_JOBS_URL}/{foreign_job['id']}", headers=headers_a)
    patch = client.patch(
        f"{_JOBS_URL}/{foreign_job['id']}",
        json={"title": "Tampered"},
        headers=headers_a,
    )
    requirement = client.post(
        f"{_JOBS_URL}/{foreign_job['id']}/requirements",
        json=_requirement_payload(),
        headers=headers_a,
    )
    requirement_patch = client.patch(
        f"{_JOBS_URL}/{own_job['id']}/requirements/{foreign_requirement.json()['id']}",
        json={"description": "Tampered"},
        headers=headers_a,
    )
    change_status = client.post(
        f"{_JOBS_URL}/{foreign_job['id']}/status",
        json={"status": "open"},
        headers=headers_a,
    )
    versions_read = client.get(f"{_JOBS_URL}/{foreign_job['id']}/versions", headers=headers_a)
    versions_write = client.post(
        f"{_JOBS_URL}/{foreign_job['id']}/versions", headers=headers_a
    )

    for response in (
        read,
        patch,
        requirement,
        requirement_patch,
        change_status,
        versions_read,
        versions_write,
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "not_found"


def test_invalid_status_transition_returns_conflict(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])

    invalid = client.post(
        f"{_JOBS_URL}/{job['id']}/status", json={"status": "closed"}, headers=headers
    )
    valid = client.post(
        f"{_JOBS_URL}/{job['id']}/status", json={"status": "open"}, headers=headers
    )

    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "conflict"
    assert valid.status_code == 200
    assert valid.json()["status"] == "open"


def test_positive_weight_requires_justification(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    payload = _requirement_payload()
    del payload["weight_justification"]

    invalid_create = client.post(
        f"{_JOBS_URL}/{job['id']}/requirements", json=payload, headers=headers
    )
    assert invalid_create.status_code == 422
    assert invalid_create.json()["error"]["code"] == "validation_error"

    created = client.post(
        f"{_JOBS_URL}/{job['id']}/requirements",
        json={**payload, "weight_justification": "Peso sintético explicado"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    requirement_id = created.json()["id"]

    invalid_update = client.patch(
        f"{_JOBS_URL}/{job['id']}/requirements/{requirement_id}",
        json={"weight": 0.7},
        headers=headers,
    )
    assert invalid_update.status_code == 422

    valid_update = client.patch(
        f"{_JOBS_URL}/{job['id']}/requirements/{requirement_id}",
        json={"weight": 0.7, "weight_justification": "Ajuste sintético"},
        headers=headers,
    )
    assert valid_update.status_code == 200
    assert valid_update.json()["weight"] == 0.7


def test_two_versions_are_created_and_listed_in_order(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])

    first = client.post(f"{_JOBS_URL}/{job['id']}/versions", headers=headers)
    second = client.post(f"{_JOBS_URL}/{job['id']}/versions", headers=headers)
    listed = client.get(f"{_JOBS_URL}/{job['id']}/versions", headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert listed.status_code == 200
    assert [version["version"] for version in listed.json()] == [1, 2]
    assert listed.json()[0]["snapshot"]["job"]["title"] == "Synthetic role"


def test_audit_records_all_job_events_without_payload(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    job_id = str(job["id"])

    updated = client.patch(
        f"{_JOBS_URL}/{job_id}", json={"title": "Synthetic role updated"}, headers=headers
    )
    changed = client.post(
        f"{_JOBS_URL}/{job_id}/status", json={"status": "open"}, headers=headers
    )
    requirement = client.post(
        f"{_JOBS_URL}/{job_id}/requirements", json=_requirement_payload(), headers=headers
    )
    requirement_patch = client.patch(
        f"{_JOBS_URL}/{job_id}/requirements/{requirement.json()['id']}",
        json={"description": "Synthetic skill updated"},
        headers=headers,
    )
    version = client.post(f"{_JOBS_URL}/{job_id}/versions", headers=headers)
    for response in (updated, changed, requirement, requirement_patch, version):
        assert response.status_code == 200 or response.status_code == 201, response.text

    events = db.scalars(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(seeded["org_a"]),
            AuditLog.action.in_(
                [
                    "job.created",
                    "job.updated",
                    "job.status_changed",
                    "requirement.added",
                    "requirement.updated",
                    "version.created",
                ]
            ),
        )
    ).all()
    assert {event.action for event in events} == {
        "job.created",
        "job.updated",
        "job.status_changed",
        "requirement.added",
        "requirement.updated",
        "version.created",
    }
    expected_resources = {
        "job.created": (UUID(job_id), "job"),
        "job.updated": (UUID(job_id), "job"),
        "job.status_changed": (UUID(job_id), "job"),
        "requirement.added": (UUID(str(requirement.json()["id"])), "requirement"),
        "requirement.updated": (UUID(str(requirement.json()["id"])), "requirement"),
        "version.created": (UUID(str(version.json()["id"])), "job_version"),
    }
    for event in events:
        assert event.actor_id == UUID(seeded["recruiter_id"])
        assert (event.resource_id, event.resource_type) == expected_resources[event.action]
        row_text = str(vars(event))
        assert _RECRUITER not in row_text
        assert _PASSWORD not in row_text

    columns = {column.name for column in AuditLog.__table__.columns}
    assert "payload" not in columns


def test_request_without_session_cookie_is_rejected(
    client: TestClient, seeded: dict[str, str]
) -> None:
    client.cookies.clear()
    headers = _org_headers(seeded["org_a"])

    read = client.get(_JOBS_URL, headers=headers)
    write = client.post(_JOBS_URL, json=_job_payload(seeded["recruiter_id"]), headers=headers)

    assert read.status_code == 401
    assert write.status_code == 401
    assert read.json()["error"]["code"] == "unauthorized"


def test_foreign_organization_header_is_rejected(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_b"])

    read = client.get(_JOBS_URL, headers=headers)
    write = client.post(_JOBS_URL, json=_job_payload(seeded["recruiter_id"]), headers=headers)

    assert read.status_code == 403
    assert write.status_code == 403
    assert read.json()["error"]["code"] == "forbidden"


def test_foreign_origin_cannot_write_jobs(client: TestClient, seeded: dict[str, str]) -> None:
    headers = {**_org_headers(seeded["org_a"]), "Origin": "https://foreign.example"}

    response = client.post(_JOBS_URL, json=_job_payload(seeded["recruiter_id"]), headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_owner_from_another_organization_is_rejected(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])

    response = client.patch(
        f"{_JOBS_URL}/{job['id']}",
        json={"owner_id": seeded["owner_b_id"]},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
