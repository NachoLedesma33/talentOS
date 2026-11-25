from __future__ import annotations

import uuid
from collections.abc import Iterator

import email_validator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.agents.models  # noqa: F401
import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.automation.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app

_URL = "/api/v1/analytics/overview"
_PASSWORD = "SyntheticPass123"
_OWNER_A = "owner-analytics@example.test"
_OWNER_B = "owner-b-analytics@example.test"


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
def client(engine: Engine) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[DBSession]:
        with DBSession(engine, expire_on_commit=False) as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "name": "Synthetic Owner"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(
        "/api/v1/organizations", json={"name": name, "slug": slug}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


def _add_application(client: TestClient, org_id: str, owner_id: str, index: int) -> None:
    headers = _headers(org_id)
    job = client.post(
        "/api/v1/jobs",
        json={"title": f"Synthetic role {index}", "owner_id": owner_id},
        headers=headers,
    )
    assert job.status_code == 201, job.text
    candidate = client.post(
        "/api/v1/candidates",
        json={
            "name": "Synthetic Candidate",
            "email": f"applicant-{index}-{org_id[:8]}@example.test",
        },
        headers=headers,
    )
    assert candidate.status_code == 201, candidate.text
    application = client.post(
        "/api/v1/applications",
        json={
            "job_id": job.json()["id"],
            "candidate_id": candidate.json()["id"],
            "source": "manual",
        },
        headers=headers,
    )
    assert application.status_code == 201, application.text


def test_overview_requires_authenticated_membership(client: TestClient) -> None:
    _register(client, _OWNER_A)
    _login(client, _OWNER_A)
    org_id = _create_org(client, "Synthetic Org", "analytics-api-org")

    response = client.get(_URL, headers=_headers(org_id))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"generated_at", "pipeline", "operational"}
    assert payload["pipeline"]["jobs_open"] == 0
    assert payload["operational"]["estimated_minutes_saved"] == 0.0
    assert "Synthetic Owner" not in response.text

    assert client.get(_URL).status_code == 403
    assert client.get(_URL, headers=_headers(str(uuid.uuid4()))).status_code == 403
    client.cookies.clear()
    assert client.get(_URL, headers=_headers(org_id)).status_code == 401


def test_overview_counts_only_active_tenant(client: TestClient) -> None:
    owner_a = _register(client, _OWNER_A)
    _login(client, _OWNER_A)
    org_a = _create_org(client, "Synthetic Org A", "analytics-api-a")
    _add_application(client, org_a, owner_a, 1)
    _add_application(client, org_a, owner_a, 2)

    owner_b = _register(client, _OWNER_B)
    _login(client, _OWNER_B)
    org_b = _create_org(client, "Synthetic Org B", "analytics-api-b")
    _add_application(client, org_b, owner_b, 3)

    _login(client, _OWNER_A)
    report_a = client.get(_URL, headers=_headers(org_a))
    assert report_a.status_code == 200, report_a.text
    stages_a = {
        item["stage"]: item for item in report_a.json()["pipeline"]["stages"]
    }
    assert stages_a["applied"]["arrivals"] == 2

    _login(client, _OWNER_B)
    report_b = client.get(_URL, headers=_headers(org_b))
    assert report_b.status_code == 200, report_b.text
    stages_b = {
        item["stage"]: item for item in report_b.json()["pipeline"]["stages"]
    }
    assert stages_b["applied"]["arrivals"] == 1
