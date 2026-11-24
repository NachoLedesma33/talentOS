from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

import email_validator
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents.matching_analyst import PROMPT_VERSION
from app.applications.models import Application
from app.assessment import service
from app.assessment.models import Assessment, RequirementEvaluation, RequirementEvaluationStatus
from app.audit.models import AuditLog
from app.candidates.models import Candidate
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.documents.extraction import (
    EXTRACTION_MODEL,
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_PROVIDER,
)
from app.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
    ExtractedField,
    ExtractedFieldName,
    ExtractedFieldStatus,
    ExtractionStatus,
)
from app.identity.models import User
from app.jobs.models import (
    Job,
    JobRequirement,
    JobVersion,
    RequirementCategory,
    RequirementImportance,
)
from app.main import app

_URL = "/api/v1/assessment"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-assessment-api@example.test"
_OWNER_B = "owner-b-assessment-api@example.test"
_RECRUITER = "recruiter-assessment-api@example.test"
_REVIEWER = "reviewer-assessment-api@example.test"

_QUOTE = "Skills: Python"
_CV_TEXT = f"{_QUOTE}\nSyntheticCvMarkerDoNotExpose\n"


@dataclass(frozen=True)
class _Scenario:
    org_id: uuid.UUID
    candidate_id: uuid.UUID
    application: Application
    job: Job
    version: JobVersion
    requirement_ids: tuple[uuid.UUID, ...]
    document: Document


class _Provider:
    """Proveedor determinista: cuenta llamadas y devuelve un dict controlado."""

    def __init__(self, output: Callable[[dict[str, object]], dict[str, object]]) -> None:
        self.output = output
        self.calls = 0

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: dict[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema
        self.calls += 1
        return self.output(context)

    def generate_text(self, prompt_version: str, context: dict[str, object]) -> str:
        del prompt_version, context
        return ""

    def health_check(self) -> bool:
        return True

    def estimate_usage(
        self, prompt_version: str, context: dict[str, object]
    ) -> dict[str, int]:
        del prompt_version, context
        return {}


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

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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


@pytest.fixture
def seeded(client: TestClient, db: DBSession) -> dict[str, str]:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Owner B"),
        (_RECRUITER, "Synthetic Recruiter"),
        (_REVIEWER, "Synthetic Reviewer"),
    ):
        _register(client, email, name)

    _login(client, _OWNER_A)
    org_a = _create_org(client, "Assessment Org A", "assessment-org-a")
    for email, role in ((_RECRUITER, "recruiter"), (_REVIEWER, "reviewer")):
        response = client.post(
            f"{_ORGS_URL}/{org_a}/members",
            json={"email": email, "role": role},
            headers={"X-Organization-ID": org_a},
        )
        assert response.status_code == 201, response.text

    _login(client, _OWNER_B)
    org_b = _create_org(client, "Assessment Org B", "assessment-org-b")
    user_ids = {
        row.email: str(row.id)
        for row in db.scalars(select(User)).all()
        if row.email in {_OWNER_A, _OWNER_B, _RECRUITER, _REVIEWER}
    }
    _login(client, _RECRUITER)
    return {
        "org_a": org_a,
        "org_b": org_b,
        "owner_a_id": user_ids[_OWNER_A],
        "owner_b_id": user_ids[_OWNER_B],
        "recruiter_id": user_ids[_RECRUITER],
        "reviewer_id": user_ids[_REVIEWER],
    }


def _headers(seeded: dict[str, str], tenant: str = "a") -> dict[str, str]:
    return {"X-Organization-ID": seeded["org_a" if tenant == "a" else "org_b"]}


def _snapshot(job: Job, items: Sequence[tuple[uuid.UUID, str]]) -> dict[str, object]:
    return {
        "job": {
            "id": str(job.id),
            "organization_id": str(job.organization_id),
            "title": job.title,
        },
        "requirements": [
            {
                "id": str(requirement_id),
                "category": RequirementCategory.SKILL.value,
                "description": description,
                "importance": RequirementImportance.REQUIRED.value,
                "expected_level": None,
                "acceptable_evidence": [],
                "weight": 0.0,
                "weight_justification": "",
            }
            for requirement_id, description in items
        ],
    }


def _seed_scenario(
    db: DBSession,
    seeded: dict[str, str],
    *,
    suffix: str,
    tenant: str = "a",
    field_status: ExtractedFieldStatus = ExtractedFieldStatus.CONFIRMED,
    version_number: int = 1,
) -> _Scenario:
    org_id = uuid.UUID(seeded["org_a" if tenant == "a" else "org_b"])
    uploader_id = uuid.UUID(seeded["owner_a_id" if tenant == "a" else "owner_b_id"])
    candidate = Candidate(
        organization_id=org_id,
        name="Synthetic Candidate",
        email=f"candidate-{suffix}-assessment@example.test",
    )
    db.add(candidate)
    db.flush()
    job = Job(organization_id=org_id, title=f"Synthetic role {suffix}", owner_id=uploader_id)
    db.add(job)
    db.flush()
    description = f"Synthetic requirement {suffix}"
    requirement = JobRequirement(
        job_id=job.id,
        category=RequirementCategory.SKILL,
        description=description,
        importance=RequirementImportance.REQUIRED,
    )
    db.add(requirement)
    db.flush()
    version = JobVersion(
        job_id=job.id,
        version=version_number,
        snapshot=_snapshot(job, [(requirement.id, description)]),
    )
    application = Application(
        organization_id=org_id, job_id=job.id, candidate_id=candidate.id
    )
    db.add_all([version, application])
    db.flush()

    document = Document(
        organization_id=org_id,
        candidate_id=candidate.id,
        uploaded_by=uploader_id,
        original_filename="synthetic-cv.pdf",
        internal_name=uuid.uuid4().hex,
        content_type="application/pdf",
        extension=".pdf",
        size_bytes=len(_CV_TEXT.encode()),
        checksum_sha256="0" * 64,
        status=DocumentStatus.PROCESSED,
        page_count=1,
    )
    db.add(document)
    db.flush()
    extraction = DocumentExtraction(
        document_id=document.id,
        provider=EXTRACTION_PROVIDER,
        model=EXTRACTION_MODEL,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        status=ExtractionStatus.COMPLETED,
        pages=[{"page": 1, "text": _CV_TEXT, "start_offset": 0, "end_offset": len(_CV_TEXT)}],
    )
    db.add(extraction)
    db.flush()
    db.add(
        ExtractedField(
            extraction_id=extraction.id,
            field_name=ExtractedFieldName.SKILLS,
            value="Python",
            status=field_status,
            evidence=[
                {
                    "document_id": str(document.id),
                    "page": 1,
                    "quote": _QUOTE,
                    "offset": 0,
                }
            ],
        )
    )
    db.commit()
    return _Scenario(
        org_id,
        candidate.id,
        application,
        job,
        version,
        (requirement.id,),
        document,
    )


def _add_version(
    db: DBSession, scenario: _Scenario, description: str, number: int
) -> uuid.UUID:
    requirement = JobRequirement(
        job_id=scenario.job.id,
        category=RequirementCategory.SKILL,
        description=description,
        importance=RequirementImportance.REQUIRED,
    )
    db.add(requirement)
    db.flush()
    db.add(
        JobVersion(
            job_id=scenario.job.id,
            version=number,
            snapshot=_snapshot(scenario.job, [(requirement.id, description)]),
        )
    )
    db.commit()
    return requirement.id


def _ref(document_id: uuid.UUID) -> dict[str, object]:
    return {
        "document_id": str(document_id),
        "field_name": "skills",
        "page": 1,
        "quote": _QUOTE,
        "offset": 0,
    }


def _result(
    requirement_id: uuid.UUID,
    status: RequirementEvaluationStatus,
    *,
    evidence_refs: Sequence[dict[str, object]] = (),
    explanation: str = "Synthetic explanation",
) -> dict[str, object]:
    return {
        "requirement_id": str(requirement_id),
        "status": status.value,
        "evidence_refs": list(evidence_refs),
        "explanation": explanation,
        "limitations": [],
        "review_required": False,
    }


def _output(
    results: Sequence[dict[str, object]],
    *,
    strengths: Sequence[str] = (),
    gaps: Sequence[str] = (),
    questions: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "evaluations": list(results),
        "strengths": list(strengths),
        "gaps": list(gaps),
        "questions": list(questions),
        "limitations": [],
        "review_required": False,
        "model_version": "mock-model-v1",
        "prompt_version": PROMPT_VERSION,
    }


def _supported_provider(document_id: uuid.UUID) -> _Provider:
    def _generate(context: dict[str, object]) -> dict[str, object]:
        requirements = context["requirements"]
        assert isinstance(requirements, list)
        return _output(
            [
                _result(
                    uuid.UUID(str(item["requirement_id"])),
                    RequirementEvaluationStatus.PARTIAL
                    if "Revised" in str(item["description"])
                    else RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[_ref(document_id)],
                    explanation="Revised synthetic explanation"
                    if "Revised" in str(item["description"])
                    else "Synthetic explanation",
                )
                for item in requirements
                if isinstance(item, dict)
            ],
            strengths=["Synthetic strength"],
        )

    return _Provider(_generate)


def _needs_review_provider() -> _Provider:
    def _generate(context: dict[str, object]) -> dict[str, object]:
        requirements = context["requirements"]
        assert isinstance(requirements, list)
        return _output(
            [
                _result(
                    uuid.UUID(str(item["requirement_id"])),
                    RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[_ref(uuid.uuid4())],
                )
                for item in requirements
                if isinstance(item, dict)
            ]
        )

    return _Provider(_generate)


def _run(client: TestClient, headers: dict[str, str], application_id: uuid.UUID):
    return client.post(
        f"{_URL}/run",
        json={"application_id": str(application_id)},
        headers=headers,
    )


def _evaluation_id(client: TestClient, headers: dict[str, str], assessment_id: str) -> str:
    detail = client.get(f"{_URL}/{assessment_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    evaluations = detail.json()["evaluations"]
    assert len(evaluations) == 1
    return str(evaluations[0]["id"])


def test_run_is_idempotent_and_list_filters_are_paginated(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(db, seeded, suffix="run")
    provider = _supported_provider(scenario.document.id)
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    headers = _headers(seeded)

    created = _run(client, headers, scenario.application.id)
    repeated = _run(client, headers, scenario.application.id)
    listing = client.get(
        _URL,
        headers=headers,
        params={
            "application_id": str(scenario.application.id),
            "candidate_id": str(scenario.candidate_id),
            "limit": 1,
            "offset": 0,
        },
    )

    assert created.status_code == 201, created.text
    assert repeated.status_code == 200, repeated.text
    body = created.json()
    assert repeated.json()["id"] == body["id"]
    assert body["status"] == "completed"
    assert body["review_required"] is False
    assert body["model_version"] == "mock-model-v1"
    assert body["prompt_version"] == PROMPT_VERSION
    assert body["summary"]["strengths"] == ["Synthetic strength"]
    assert body["evaluations"][0]["evidence"][0]["quote"] == _QUOTE
    assert provider.calls == 1
    assert db.scalar(select(func.count()).select_from(Assessment)) == 1
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert [item["id"] for item in listing.json()["items"]] == [body["id"]]
    assert "organization_id" not in listing.text


def test_detail_shows_review_flag_and_evidence_without_cv_or_storage_paths(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(db, seeded, suffix="detail")
    monkeypatch.setattr(
        service, "get_llm_provider", lambda: _supported_provider(scenario.document.id)
    )
    headers = _headers(seeded)
    created = _run(client, headers, scenario.application.id)
    assert created.status_code == 201, created.text
    assessment_id = str(created.json()["id"])

    detail = client.get(f"{_URL}/{assessment_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert set(("evaluations", "summary", "limitations", "model_version", "prompt_version")) <= set(
        body
    )
    assert set(body["summary"]) == {"strengths", "gaps", "questions"}
    assert body["evaluations"][0]["status"] == "supported"
    assert body["review_required"] is False
    assert _QUOTE in detail.text
    assert "SyntheticCvMarkerDoNotExpose" not in detail.text
    assert "organization_id" not in body
    assert "internal_name" not in detail.text
    assert "storage" not in detail.text

    _login(client, _OWNER_B)
    foreign = client.get(f"{_URL}/{assessment_id}", headers=_headers(seeded, "b"))
    wrong_org = client.get(f"{_URL}/{assessment_id}", headers=headers)
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"
    assert wrong_org.status_code == 403


def test_compare_versions_and_reject_foreign_tenant_and_other_application(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(db, seeded, suffix="compare")
    monkeypatch.setattr(
        service, "get_llm_provider", lambda: _supported_provider(scenario.document.id)
    )
    headers = _headers(seeded)
    first = _run(client, headers, scenario.application.id)
    assert first.status_code == 201, first.text
    first_id = str(first.json()["id"])
    revised_id = _add_version(db, scenario, "Revised synthetic requirement", 2)

    second = _run(client, headers, scenario.application.id)
    assert second.status_code == 201, second.text
    second_id = str(second.json()["id"])
    assert second_id != first_id

    comparison = client.get(
        f"{_URL}/{first_id}/compare", params={"other_id": second_id}, headers=headers
    )
    assert comparison.status_code == 200, comparison.text
    body = comparison.json()
    assert body["base"]["assessment_id"] == first_id
    assert body["target"]["assessment_id"] == second_id
    assert body["base"]["model_version"] == "mock-model-v1"
    assert body["base"]["prompt_version"] == PROMPT_VERSION
    revised = [
        item for item in body["changes"] if str(item["requirement_id"]) == str(revised_id)
    ]
    assert len(revised) == 1
    assert revised[0]["status"] == {"before": None, "after": "partial", "changed": True}
    assert revised[0]["evidence_refs"]["changed"] is True
    assert revised[0]["review_required"]["changed"] is True

    _login(client, _OWNER_B)
    foreign = client.get(
        f"{_URL}/{first_id}/compare",
        params={"other_id": second_id},
        headers=_headers(seeded, "b"),
    )
    assert foreign.status_code == 404

    _login(client, _RECRUITER)
    other = _seed_scenario(db, seeded, suffix="other-app")
    monkeypatch.setattr(
        service, "get_llm_provider", lambda: _supported_provider(other.document.id)
    )
    third = _run(client, headers, other.application.id)
    assert third.status_code == 201, third.text
    mismatch = client.get(
        f"{_URL}/{first_id}/compare",
        params={"other_id": str(third.json()["id"])},
        headers=headers,
    )
    assert mismatch.status_code == 400
    assert "misma postulación" in mismatch.json()["error"]["message"]


def test_review_records_actor_time_and_audit_but_reviewer_is_forbidden(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(db, seeded, suffix="review")
    monkeypatch.setattr(service, "get_llm_provider", lambda: _needs_review_provider())
    headers = _headers(seeded)
    created = _run(client, headers, scenario.application.id)
    assert created.status_code == 201, created.text
    assessment_id = str(created.json()["id"])
    evaluation_id = _evaluation_id(client, headers, assessment_id)
    url = f"{_URL}/{assessment_id}/evaluations/{evaluation_id}/review"

    _login(client, _REVIEWER)
    denied = client.patch(
        url, json={"status": "supported"}, headers=headers
    )
    assert denied.status_code == 403

    _login(client, _RECRUITER)
    invalid = client.patch(url, json={"status": "hired"}, headers=headers)
    assert invalid.status_code == 422

    note = "Synthetic review note"
    response = client.patch(
        url, json={"status": "supported", "explanation": f"  {note}  "}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "supported"
    assert body["reviewed_by"] == seeded["recruiter_id"]
    assert body["reviewed_at"]
    assert body["review_required"] is False
    assert body["explanation"] == note

    db.expire_all()
    stored = db.get(RequirementEvaluation, uuid.UUID(evaluation_id))
    assert stored is not None
    assert stored.reviewed_by == uuid.UUID(seeded["recruiter_id"])
    assert stored.reviewed_at is not None
    assert stored.status is RequirementEvaluationStatus.SUPPORTED
    events = db.scalars(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(seeded["org_a"]),
            AuditLog.action == "assessment.reviewed",
        )
    ).all()
    assert len(events) == 1
    assert str(events[0].actor_id) == seeded["recruiter_id"]
    assert str(events[0].resource_id) == assessment_id
    assert note not in str(events[0].__dict__)


def test_review_complete_conflicts_with_pending_then_succeeds(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(db, seeded, suffix="complete")
    monkeypatch.setattr(service, "get_llm_provider", lambda: _needs_review_provider())
    headers = _headers(seeded)
    created = _run(client, headers, scenario.application.id)
    assert created.status_code == 201, created.text
    assessment_id = str(created.json()["id"])
    complete_url = f"{_URL}/{assessment_id}/review-complete"

    pending = client.post(complete_url, headers=headers)
    assert pending.status_code == 409
    message = pending.json()["error"]["message"]
    assert "needs_review" in message
    assert "Revíselos" in message

    evaluation_id = _evaluation_id(client, headers, assessment_id)
    review = client.patch(
        f"{_URL}/{assessment_id}/evaluations/{evaluation_id}/review",
        json={"status": "supported"},
        headers=headers,
    )
    assert review.status_code == 200, review.text
    done = client.post(complete_url, headers=headers)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["review_required"] is False
    events = db.scalars(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(seeded["org_a"]),
            AuditLog.action == "assessment.review_completed",
        )
    ).all()
    assert len(events) == 1
    assert str(events[0].resource_id) == assessment_id


def test_missing_cookie_foreign_application_and_foreign_origin_are_rejected(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(db, seeded, suffix="authz")
    provider = _supported_provider(scenario.document.id)
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    headers = _headers(seeded)

    client.cookies.clear()
    assert client.get(_URL, headers=headers).status_code == 401
    assert _run(client, headers, scenario.application.id).status_code == 401

    _login(client, _OWNER_B)
    foreign = _run(client, _headers(seeded, "b"), scenario.application.id)
    wrong_org = _run(client, headers, scenario.application.id)
    assert foreign.status_code == 404
    assert wrong_org.status_code == 403
    assert provider.calls == 0

    _login(client, _RECRUITER)
    bad_origin = client.post(
        f"{_URL}/run",
        json={"application_id": str(scenario.application.id)},
        headers={**headers, "Origin": "https://foreign.example"},
    )
    assert bad_origin.status_code == 403

    clean = _run(client, headers, scenario.application.id)
    assert clean.status_code == 201, clean.text


def test_without_confirmed_fields_returns_not_found_without_provider_call(
    client: TestClient, db: DBSession, seeded: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _seed_scenario(
        db, seeded, suffix="unconfirmed", field_status=ExtractedFieldStatus.EXTRACTED
    )
    provider = _supported_provider(scenario.document.id)
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = _run(client, _headers(seeded), scenario.application.id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert provider.calls == 0
    assert body["status"] == "needs_review"
    assert body["review_required"] is True
    assert "no_confirmed_fields" in body["limitations"]
    assert body["evaluations"][0]["status"] == "not_found"
    assert body["evaluations"][0]["review_required"] is True
