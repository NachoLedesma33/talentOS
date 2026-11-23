from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import email_validator
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

# Registrar tablas al importar: `test_auth` recarga `app.db.base` al terminar y
# los modelos importados después quedarían en una metadata distinta de `Base`.
import app.applications.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.audit.models import AuditLog
from app.db.base import Base
from app.db.session import get_db
from app.main import app

_URL = "/api/v1/applications"
_ORGS_URL = "/api/v1/organizations"
_JOBS_URL = "/api/v1/jobs"
_CANDIDATES_URL = "/api/v1/candidates"
_PASSWORD = "SyntheticPass123"

_OWNER_A = "owner-applications@example.test"
_OWNER_B = "owner-b-applications@example.test"
_RECRUITER = "recruiter-applications@example.test"
_VIEWER = "viewer-applications@example.test"
_REVIEWER = "reviewer-applications@example.test"

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
    _register(client, _REVIEWER, "Synthetic Reviewer")
    _register(client, _VIEWER, "Synthetic Viewer")
    owner_b_id = _register(client, _OWNER_B, "Synthetic Owner B")

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Org A", "applications-org-a")
    headers_a = _org_headers(org_a)
    for email, role in ((_RECRUITER, "recruiter"), (_REVIEWER, "reviewer"), (_VIEWER, "viewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers=headers_a,
        )
        assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Org B", "applications-org-b")
    _login(client, _RECRUITER)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "owner_b_id": owner_b_id,
        "recruiter_id": recruiter_id,
    }


def _register(client: TestClient, email: str, name: str) -> str:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD, "name": name}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200, response.text


def _create_org(client: TestClient, name: str, slug: str) -> str:
    response = client.post(_ORGS_URL, json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _org_headers(org_id: str) -> dict[str, str]:
    return {"X-Organization-ID": org_id}


def _create_job(client: TestClient, headers: dict[str, str], owner_id: str) -> dict[str, object]:
    response = client.post(
        _JOBS_URL, json={"title": "Synthetic role", "owner_id": owner_id}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_candidate(
    client: TestClient, headers: dict[str, str], email: str = "applicant@example.test"
) -> dict[str, object]:
    response = client.post(
        _CANDIDATES_URL,
        json={"name": "Synthetic Candidate", "email": email},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_application(
    client: TestClient, headers: dict[str, str], job_id: str, candidate_id: str
) -> dict[str, object]:
    response = client.post(
        _URL,
        json={"job_id": job_id, "candidate_id": candidate_id, "source": "manual"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _change_stage(
    client: TestClient, headers: dict[str, str], application_id: str, to_stage: str
) -> Response:
    return client.post(
        f"{_URL}/{application_id}/stage", json={"to_stage": to_stage}, headers=headers
    )


def _advance_to(
    client: TestClient, headers: dict[str, str], application_id: str, stage: str
) -> None:
    path: dict[str, list[str]] = {
        "applied": [],
        "screening": ["screening"],
        "interview": ["screening", "interview"],
        "offer": ["screening", "interview", "offer"],
        "hired": ["screening", "interview", "offer", "hired"],
        "rejected": ["rejected"],
    }
    for step in path[stage]:
        response = _change_stage(client, headers, application_id, step)
        assert response.status_code == 200, response.text


def test_create_application_starts_applied_with_initial_stage_change(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))

    detail = client.get(f"{_URL}/{application['id']}", headers=headers)
    history = client.get(f"{_URL}/{application['id']}/history", headers=headers)
    listing = client.get(
        _URL,
        headers=headers,
        params={
            "job_id": job["id"],
            "candidate_id": candidate["id"],
            "stage": "applied",
            "limit": 2,
            "offset": 0,
        },
    )

    assert application["stage"] == "applied"
    assert application["source"] == "manual"
    assert "organization_id" not in application
    assert not _PROTECTED_FIELDS & set(application)
    assert detail.status_code == 200
    # SQLite devuelve datetimes naive: comparar campos estables del contrato.
    assert all(
        detail.json()[key] == application[key]
        for key in ("id", "job_id", "candidate_id", "stage", "source")
    )
    assert [item["id"] for item in listing.json()["items"]] == [application["id"]]
    assert (listing.json()["total"], listing.json()["limit"], listing.json()["offset"]) == (
        1,
        2,
        0,
    )
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["from_stage"] is None
    assert history.json()[0]["to_stage"] == "applied"
    assert history.json()[0]["actor_id"] == seeded["recruiter_id"]
    assert history.json()[0]["note"] is None


def test_duplicate_application_is_conflict(client: TestClient, seeded: dict[str, str]) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    _create_application(client, headers, str(job["id"]), str(candidate["id"]))

    duplicate = client.post(
        _URL, json={"job_id": job["id"], "candidate_id": candidate["id"]}, headers=headers
    )
    listing = client.get(_URL, headers=headers)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
    assert listing.json()["total"] == 1


def test_job_or_candidate_from_other_organization_is_not_found(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job_a = _create_job(client, headers, seeded["recruiter_id"])
    candidate_a = _create_candidate(client, headers, "local-applicant@example.test")

    _login(client, _OWNER_B)
    foreign_headers = _org_headers(seeded["org_b"])
    job_b = _create_job(client, foreign_headers, seeded["owner_b_id"])
    candidate_b = _create_candidate(client, foreign_headers, "foreign-applicant@example.test")

    _login(client, _RECRUITER)
    foreign_job = client.post(
        _URL,
        json={"job_id": job_b["id"], "candidate_id": candidate_a["id"]},
        headers=headers,
    )
    foreign_candidate = client.post(
        _URL,
        json={"job_id": job_a["id"], "candidate_id": candidate_b["id"]},
        headers=headers,
    )

    for response in (foreign_job, foreign_candidate):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "not_found"
    assert client.get(_URL, headers=headers).json()["total"] == 0


def test_cross_tenant_application_detail_history_and_stage_are_not_revealed(
    client: TestClient, seeded: dict[str, str]
) -> None:
    _login(client, _OWNER_B)
    foreign_headers = _org_headers(seeded["org_b"])
    job_b = _create_job(client, foreign_headers, seeded["owner_b_id"])
    candidate_b = _create_candidate(client, foreign_headers, "foreign-app@example.test")
    foreign = _create_application(
        client, foreign_headers, str(job_b["id"]), str(candidate_b["id"])
    )

    _login(client, _RECRUITER)
    headers = _org_headers(seeded["org_a"])
    detail = client.get(f"{_URL}/{foreign['id']}", headers=headers)
    history = client.get(f"{_URL}/{foreign['id']}/history", headers=headers)
    stage = _change_stage(client, headers, str(foreign["id"]), "screening")
    listing = client.get(_URL, headers=headers)

    for response in (detail, history, stage):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "not_found"
    assert listing.json()["total"] == 0


def test_valid_transitions_are_applied_in_order(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    application_id = str(application["id"])

    for target in ("screening", "interview", "offer", "hired"):
        response = _change_stage(client, headers, application_id, target)
        assert response.status_code == 200, response.text
        assert response.json()["to_stage"] == target
        detail = client.get(f"{_URL}/{application_id}", headers=headers)
        assert detail.json()["stage"] == target

    history = client.get(f"{_URL}/{application_id}/history", headers=headers).json()
    assert [(change["from_stage"], change["to_stage"]) for change in history] == [
        (None, "applied"),
        ("applied", "screening"),
        ("screening", "interview"),
        ("interview", "offer"),
        ("offer", "hired"),
    ]
    assert all(change["actor_id"] == seeded["recruiter_id"] for change in history)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("applied", "interview"),
        ("applied", "offer"),
        ("applied", "hired"),
        ("applied", "applied"),
        ("screening", "offer"),
        ("screening", "hired"),
        ("interview", "hired"),
        ("interview", "applied"),
        ("offer", "screening"),
        ("offer", "applied"),
    ],
)
def test_invalid_transitions_are_conflict(
    client: TestClient, seeded: dict[str, str], current: str, target: str
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    application_id = str(application["id"])
    _advance_to(client, headers, application_id, current)

    response = _change_stage(client, headers, application_id, target)
    detail = client.get(f"{_URL}/{application_id}", headers=headers)
    history = client.get(f"{_URL}/{application_id}/history", headers=headers)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "conflict"
    assert detail.json()["stage"] == current
    assert len(history.json()) == (
        1 if current == "applied" else {"screening": 2, "interview": 3, "offer": 4}[current]
    )


@pytest.mark.parametrize("terminal", ["hired", "rejected"])
def test_terminal_stages_reject_every_change(
    client: TestClient, seeded: dict[str, str], terminal: str
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    application_id = str(application["id"])
    _advance_to(client, headers, application_id, terminal)

    for target in ("applied", "screening", "interview", "offer", "hired", "rejected"):
        response = _change_stage(client, headers, application_id, target)
        assert response.status_code == 409, response.text

    assert client.get(f"{_URL}/{application_id}", headers=headers).json()["stage"] == terminal


def test_viewer_can_read_pipeline_but_cannot_write(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    _login(client, _VIEWER)

    listing = client.get(_URL, headers=headers)
    detail = client.get(f"{_URL}/{application['id']}", headers=headers)
    history = client.get(f"{_URL}/{application['id']}/history", headers=headers)
    create = client.post(
        _URL, json={"job_id": job["id"], "candidate_id": candidate["id"]}, headers=headers
    )
    stage = _change_stage(client, headers, str(application["id"]), "screening")

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert history.status_code == 200
    assert create.status_code == 403
    assert stage.status_code == 403
    assert create.json()["error"]["code"] == "forbidden"


def test_audit_and_history_record_actor_and_note(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers, "audited-applicant@example.test")
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    application_id = str(application["id"])
    actor_id = seeded["recruiter_id"]

    changed = client.post(
        f"{_URL}/{application_id}/stage",
        json={"to_stage": "screening", "note": "  Synthetic screening note  "},
        headers=headers,
    )
    history = client.get(f"{_URL}/{application_id}/history", headers=headers)
    events = db.scalars(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(seeded["org_a"]),
            AuditLog.action.in_({"application.created", "application.stage_changed"}),
        )
    ).all()

    assert changed.status_code == 200
    assert changed.json()["note"] == "Synthetic screening note"
    assert changed.json()["actor_id"] == actor_id
    assert history.status_code == 200
    assert history.json()[-1]["note"] == "Synthetic screening note"

    assert {event.action for event in events} == {
        "application.created",
        "application.stage_changed",
    }
    for event in events:
        assert str(event.actor_id) == actor_id
        assert event.resource_type == "application"
        assert str(event.resource_id) == application_id
        assert "audited-applicant@example.test" not in str(vars(event))


def test_requests_without_session_are_rejected(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    client.cookies.clear()

    responses = [
        client.get(_URL, headers=headers),
        client.get(f"{_URL}/{application['id']}", headers=headers),
        client.get(f"{_URL}/{application['id']}/history", headers=headers),
        client.post(
            _URL, json={"job_id": job["id"], "candidate_id": candidate["id"]}, headers=headers
        ),
        _change_stage(client, headers, str(application["id"]), "screening"),
    ]

    for response in responses:
        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "unauthorized"


def test_foreign_organization_header_is_forbidden(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    foreign_headers = _org_headers(seeded["org_b"])

    responses = [
        client.get(_URL, headers=foreign_headers),
        client.get(f"{_URL}/{application['id']}", headers=foreign_headers),
        client.get(f"{_URL}/{application['id']}/history", headers=foreign_headers),
        client.post(
            _URL,
            json={"job_id": job["id"], "candidate_id": candidate["id"]},
            headers=foreign_headers,
        ),
        _change_stage(client, foreign_headers, str(application["id"]), "screening"),
    ]

    for response in responses:
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "forbidden"


def test_foreign_origin_is_rejected_on_writes(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))
    foreign_origin = {**headers, "Origin": "https://foreign.example"}

    create = client.post(
        _URL, json={"job_id": job["id"], "candidate_id": candidate["id"]}, headers=foreign_origin
    )
    stage = client.post(
        f"{_URL}/{application['id']}/stage",
        json={"to_stage": "screening"},
        headers=foreign_origin,
    )

    for response in (create, stage):
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "forbidden"


def test_unknown_enums_and_organization_id_are_rejected(
    client: TestClient, seeded: dict[str, str]
) -> None:
    headers = _org_headers(seeded["org_a"])
    job = _create_job(client, headers, seeded["recruiter_id"])
    candidate = _create_candidate(client, headers)
    application = _create_application(client, headers, str(job["id"]), str(candidate["id"]))

    bad_source = client.post(
        _URL,
        json={
            "job_id": job["id"],
            "candidate_id": candidate["id"],
            "source": "unknown",
        },
        headers=headers,
    )
    bad_stage = _change_stage(client, headers, str(application["id"]), "unknown")
    injected_org = client.post(
        _URL,
        json={
            "job_id": job["id"],
            "candidate_id": candidate["id"],
            "organization_id": seeded["org_b"],
        },
        headers=headers,
    )

    for response in (bad_source, bad_stage, injected_org):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "validation_error"
