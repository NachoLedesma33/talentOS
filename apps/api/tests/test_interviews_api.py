from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import cast

import email_validator
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.applications.models  # noqa: F401
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.interviews.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents.interview_assistant import PROMPT_VERSION
from app.applications.models import Application
from app.assessment.models import AssessmentStatus, RequirementEvaluationStatus
from app.assessment.repositories import create_assessment, save_evaluation, update_summary
from app.audit.service import list_resource_events
from app.candidates.models import Candidate
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.identity.models import User
from app.interviews import service as interviews_service
from app.interviews.models import (
    InterviewFeedbackStatus,
    InterviewGuideStatus,
    InterviewQuestionStatus,
)
from app.interviews.service import MANUAL_PROMPT_VERSION
from app.jobs.models import (
    Job,
    JobRequirement,
    JobVersion,
    RequirementCategory,
    RequirementImportance,
)
from app.main import app

_URL = "/api/v1/interviews"
_ORGS_URL = "/api/v1/organizations"
_PASSWORD = "SyntheticPass123"
_COOKIE = get_settings().SESSION_COOKIE_NAME

_OWNER_A = "owner-interviews-api@example.test"
_OWNER_B = "owner-b-interviews-api@example.test"
_REVIEWER = "reviewer-interviews-api@example.test"

_CV_MARKER = "SyntheticCvMarkerDoNotExpose"
_QUESTION = "¿Cómo aplicó Python en servicios backend?"
_FOCUS = "Evidencia profesional acotada al requisito"
_COMPETENCY = "Python backend"


@dataclass(frozen=True)
class _Scenario:
    org_a: str
    org_b: str
    owner_id: uuid.UUID
    application: Application
    version: JobVersion
    requirement_id: uuid.UUID


class _Provider:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls = 0

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema, context
        self.calls += 1
        return self.output

    def generate_text(self, prompt_version: str, context: Mapping[str, object]) -> str:
        del prompt_version, context
        return ""

    def health_check(self) -> bool:
        return True

    def estimate_usage(
        self, prompt_version: str, context: Mapping[str, object]
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


@pytest.fixture
def seeded(client: TestClient, db: DBSession) -> dict[str, str]:
    for email, name in (
        (_OWNER_A, "Synthetic Owner A"),
        (_OWNER_B, "Synthetic Owner B"),
        (_REVIEWER, "Synthetic Reviewer"),
    ):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": _PASSWORD, "name": name},
        )
        assert response.status_code == 201, response.text

    response = client.post(
        "/api/v1/auth/login", json={"email": _OWNER_A, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    created_org = client.post(
        _ORGS_URL, json={"name": "Interviews A", "slug": "interviews-a"}
    )
    assert created_org.status_code == 201, created_org.text
    org_a = str(created_org.json()["id"])
    response = client.post(
        f"{_ORGS_URL}/{org_a}/members",
        json={"email": _REVIEWER, "role": "reviewer"},
        headers={"X-Organization-ID": org_a},
    )
    assert response.status_code == 201, response.text

    response = client.post(
        "/api/v1/auth/login", json={"email": _OWNER_B, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    created_org = client.post(
        _ORGS_URL, json={"name": "Interviews B", "slug": "interviews-b"}
    )
    assert created_org.status_code == 201, created_org.text
    org_b = str(created_org.json()["id"])

    ids = {
        row.email: str(row.id)
        for row in db.scalars(select(User)).all()
        if row.email in {_OWNER_A, _OWNER_B, _REVIEWER}
    }
    return {
        "org_a": org_a,
        "org_b": org_b,
        "owner_a_id": ids[_OWNER_A],
        "owner_b_id": ids[_OWNER_B],
        "reviewer_id": ids[_REVIEWER],
    }


def _login(client: TestClient, email: str) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})
    assert login.status_code == 200, login.text
    assert _COOKIE in client.cookies
    return {}


def _headers(seeded: dict[str, str], tenant: str = "a") -> dict[str, str]:
    return {"X-Organization-ID": seeded["org_a" if tenant == "a" else "org_b"]}


def _seed_scenario(db: DBSession, seeded: dict[str, str], suffix: str) -> _Scenario:
    org_id = uuid.UUID(seeded["org_a"])
    owner_id = uuid.UUID(seeded["owner_a_id"])
    candidate = Candidate(
        organization_id=org_id,
        name="Synthetic Candidate",
        email=f"candidate-{suffix}-interviews@example.test",
    )
    db.add(candidate)
    db.flush()
    job = Job(organization_id=org_id, title=f"Synthetic role {suffix}", owner_id=owner_id)
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
        version=1,
        snapshot={
            "job": {"id": str(job.id), "organization_id": str(org_id)},
            "requirements": [
                {
                    "id": str(requirement.id),
                    "category": RequirementCategory.SKILL.value,
                    "description": description,
                    "importance": RequirementImportance.REQUIRED.value,
                }
            ],
        },
    )
    application = Application(
        organization_id=org_id, job_id=job.id, candidate_id=candidate.id
    )
    db.add_all([version, application])
    db.flush()
    assessment = create_assessment(
        db,
        organization_id=org_id,
        application_id=application.id,
        job_version_id=version.id,
        candidate_id=candidate.id,
        created_by=owner_id,
        model_version="mock-matching-v1",
        prompt_version="matching-v1",
    )
    save_evaluation(
        db,
        assessment_id=assessment.id,
        requirement_id=requirement.id,
        status=RequirementEvaluationStatus.PARTIAL,
        explanation="Synthetic partial evidence",
        evidence=[],
        limitations=[],
        review_required=True,
    )
    update_summary(
        db,
        assessment,
        status=AssessmentStatus.NEEDS_REVIEW,
        summary={"strengths": [], "gaps": [], "questions": []},
        limitations=[],
    )
    db.commit()
    return _Scenario(
        seeded["org_a"], seeded["org_b"], owner_id, application, version, requirement.id
    )


def _provider(requirement_id: uuid.UUID) -> _Provider:
    return _Provider(
        {
            "questions": [
                {
                    "requirement_id": str(requirement_id),
                    "category": "technical",
                    "question": _QUESTION,
                    "evidence_focus": _FOCUS,
                    "competency": _COMPETENCY,
                    "limitations": [],
                }
            ],
            "model_version": "mock-model-v1",
            "prompt_version": PROMPT_VERSION,
            "limitations": [],
            "review_required": False,
        }
    )


def _generate(
    client: TestClient, scenario: _Scenario, seeded: dict[str, str], provider: _Provider
) -> dict[str, object]:
    original = interviews_service.get_llm_provider
    interviews_service.get_llm_provider = lambda: provider  # type: ignore[assignment]
    try:
        response = client.post(
            f"{_URL}/guides/generate",
            json={"application_id": str(scenario.application.id)},
            headers=_headers(seeded),
        )
    finally:
        interviews_service.get_llm_provider = original
    assert response.status_code in {200, 201}, response.text
    return cast(dict[str, object], response.json())


def _questions(
    client: TestClient, headers: dict[str, str], guide_id: str
) -> list[dict[str, object]]:
    detail = client.get(f"{_URL}/guides/{guide_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    return cast(list[dict[str, object]], detail.json()["questions"])


def _audit_actions(db: DBSession, org_id: uuid.UUID, resource_id: uuid.UUID) -> list[str]:
    return [
        entry.action
        for entry in list_resource_events(db, org_id, "interview_guide", resource_id)
    ]


def test_auth_and_tenant_boundaries(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "auth")
    body = {"application_id": str(scenario.application.id)}

    client.cookies.clear()
    anonymous = client.post(f"{_URL}/guides/generate", json=body, headers=_headers(seeded))
    assert anonymous.status_code == 401, anonymous.text

    _login(client, _OWNER_A)
    foreign = client.post(f"{_URL}/guides/generate", json=body, headers=_headers(seeded, "b"))
    assert foreign.status_code == 403, foreign.text

    missing = client.get(f"{_URL}/guides/{uuid.uuid4()}", headers=_headers(seeded))
    assert missing.status_code == 404, missing.text

    generated = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    guide_id = str(generated["guide_id"])
    question_id = str(cast(list[dict[str, object]], generated["questions"])[0]["id"])

    _login(client, _REVIEWER)
    reviewer_write = client.patch(
        f"{_URL}/guides/{guide_id}",
        json={"title": "Synthetic title"},
        headers=_headers(seeded),
    )
    assert reviewer_write.status_code == 403, reviewer_write.text
    reviewer_feedback = client.post(
        f"{_URL}/questions/{question_id}/feedback",
        json={"observed_evidence": [], "gaps": [], "follow_up_needed": False},
        headers=_headers(seeded),
    )
    assert reviewer_feedback.status_code == 403, reviewer_feedback.text

    _login(client, _OWNER_A)
    foreign_guide = client.get(f"{_URL}/guides/{guide_id}", headers=_headers(seeded, "b"))
    assert foreign_guide.status_code == 403, foreign_guide.text
    foreign_question = client.delete(
        f"{_URL}/questions/{question_id}", headers=_headers(seeded, "b")
    )
    assert foreign_question.status_code == 403, foreign_question.text


def test_generate_is_idempotent_and_audited(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "generate")
    _login(client, _OWNER_A)
    provider = _provider(scenario.requirement_id)
    first = _generate(client, scenario, seeded, provider)
    second = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    assert provider.calls == 1
    assert first["created"] is True
    assert second["created"] is False
    assert first["guide_id"] == second["guide_id"]
    assert first["status"] == InterviewGuideStatus.DRAFT.value
    assert len(cast(list[object], first["questions"])) == 1

    guides = client.get(f"{_URL}/guides", headers=_headers(seeded))
    assert guides.status_code == 200, guides.text
    assert guides.json()["total"] == 1
    guide_id = str(first["guide_id"])
    assert _audit_actions(db, uuid.UUID(scenario.org_a), uuid.UUID(guide_id)).count(
        "interview.guide_generated"
    ) == 1


def test_list_filters_pagination_and_detail_sanitization(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "list")
    _login(client, _OWNER_A)
    generated = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    guide_id = str(generated["guide_id"])

    bad_limit = client.get(f"{_URL}/guides?limit=0", headers=_headers(seeded))
    assert bad_limit.status_code == 422, bad_limit.text
    filtered = client.get(
        f"{_URL}/guides",
        params={
            "application_id": str(scenario.application.id),
            "status": "draft",
            "limit": 1,
            "offset": 0,
        },
        headers=_headers(seeded),
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == guide_id

    detail = client.get(f"{_URL}/guides/{guide_id}", headers=_headers(seeded))
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert "organization_id" not in body
    assert "cv" not in str(body).casefold()
    assert _CV_MARKER not in detail.text
    question = body["questions"][0]
    for key in (
        "requirement_id",
        "category",
        "question",
        "evidence_focus",
        "competency",
        "status",
        "position",
        "review_required",
        "model_version",
        "prompt_version",
    ):
        assert key in question
    assert "evidence_refs" not in question


def test_revisions_are_paginated_and_sanitized(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "revisions")
    _login(client, _OWNER_A)
    generated = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    guide_id = str(generated["guide_id"])
    response = client.post(
        f"{_URL}/guides/{guide_id}/questions",
        json={
            "requirement_id": str(scenario.requirement_id),
            "position": 2,
            "category": "deep_dive",
            "question": "¿Cómo resolvió un fallo de API con evidencia parcial?",
            "evidence_focus": "Decisión técnica y verificación",
            "competency": "API design",
        },
        headers=_headers(seeded),
    )
    assert response.status_code == 201, response.text

    revisions = client.get(
        f"{_URL}/guides/{guide_id}/revisions",
        params={"limit": 1, "offset": 0},
        headers=_headers(seeded),
    )
    assert revisions.status_code == 200, revisions.text
    payload = revisions.json()
    assert payload["total"] >= 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["created_by"] == seeded["owner_a_id"]
    assert "cv" not in str(payload["items"][0]["snapshot"]).casefold()

    assert (
        client.get(
            f"{_URL}/guides/{uuid.uuid4()}/revisions", headers=_headers(seeded)
        ).status_code
        == 404
    )


def test_guide_transition_version_revision_and_publish_guard(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "publish")
    _login(client, _OWNER_A)
    generated = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    guide_id = str(generated["guide_id"])
    flagged = client.post(
        f"{_URL}/guides/{guide_id}/questions",
        json={
            "requirement_id": str(scenario.requirement_id),
            "position": 2,
            "category": "deep_dive",
            "question": "¿Cómo verificó una decisión de diseño con datos incompletos?",
            "evidence_focus": "Razonamiento y verificación",
            "competency": "API design",
            "review_required": True,
        },
        headers=_headers(seeded),
    )
    assert flagged.status_code == 201, flagged.text
    question_id = str(flagged.json()["id"])
    assert flagged.json()["review_required"] is True
    blocked = client.patch(
        f"{_URL}/guides/{guide_id}",
        json={"status": "published"},
        headers=_headers(seeded),
    )
    assert blocked.status_code == 409, blocked.text
    assert "Corr" in blocked.json()["error"]["message"]

    approved = client.patch(
        f"{_URL}/questions/{question_id}",
        json={"status": "approved"},
        headers=_headers(seeded),
    )
    assert approved.status_code == 200, approved.text
    published = client.patch(
        f"{_URL}/guides/{guide_id}",
        json={"title": "Synthetic published title", "status": "published"},
        headers={
            "X-Organization-ID": seeded["org_a"],
            "X-Request-ID": "req-publish",
            "X-Correlation-ID": "corr-publish",
        },
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["version"] > int(generated["version"])
    assert published.headers["x-request-id"] == "req-publish"
    assert published.headers["x-correlation-id"] == "corr-publish"

    history = client.get(
        f"{_URL}/guides/{guide_id}/revisions", headers=_headers(seeded)
    ).json()
    assert history["total"] > 1
    assert "interview.guide_updated" in _audit_actions(
        db, uuid.UUID(scenario.org_a), uuid.UUID(guide_id)
    )
    invalid = client.patch(
        f"{_URL}/guides/{guide_id}",
        json={"status": "draft"},
        headers=_headers(seeded),
    )
    assert invalid.status_code == 409, invalid.text


def test_manual_question_policy_revision_and_soft_delete(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "questions")
    _login(client, _OWNER_A)
    generated = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    guide_id = str(generated["guide_id"])
    base = {
        "requirement_id": str(scenario.requirement_id),
        "position": 2,
        "category": "deep_dive",
        "question": "¿Qué evidencia aportó sobre APIs en producción?",
        "evidence_focus": "Caso concreto y resultado",
        "competency": "API design",
    }
    created = client.post(
        f"{_URL}/guides/{guide_id}/questions", json=base, headers=_headers(seeded)
    )
    assert created.status_code == 201, created.text
    question_id = str(created.json()["id"])
    assert created.json()["prompt_version"] == MANUAL_PROMPT_VERSION
    assert "interview.question_added" in [
        entry.action
        for entry in list_resource_events(
            db, uuid.UUID(scenario.org_a), "interview_question", uuid.UUID(question_id)
        )
    ]

    discriminatory = client.post(
        f"{_URL}/guides/{guide_id}/questions",
        json={
            **base,
            "position": 3,
            "question": "¿Tiene hijos o planes de maternidad?",
        },
        headers=_headers(seeded),
    )
    assert discriminatory.status_code == 422, discriminatory.text
    assert discriminatory.json()["error"]["reason_code"] == "protected_family"

    moved = client.patch(
        f"{_URL}/questions/{question_id}",
        json={"position": 2, "status": "approved"},
        headers=_headers(seeded),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == InterviewQuestionStatus.APPROVED.value
    archived = client.delete(
        f"{_URL}/questions/{question_id}", headers=_headers(seeded)
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == InterviewQuestionStatus.ARCHIVED.value
    remaining = _questions(client, _headers(seeded), guide_id)
    assert question_id not in [item["id"] for item in remaining]

    invalid_transition = client.patch(
        f"{_URL}/questions/{question_id}",
        json={"status": "draft"},
        headers=_headers(seeded),
    )
    assert invalid_transition.status_code == 409, invalid_transition.text


def test_feedback_has_no_score_or_decision_and_is_tenant_scoped(
    client: TestClient, seeded: dict[str, str], db: DBSession
) -> None:
    scenario = _seed_scenario(db, seeded, "feedback")
    _login(client, _OWNER_A)
    generated = _generate(client, scenario, seeded, _provider(scenario.requirement_id))
    question_id = str(cast(list[dict[str, object]], generated["questions"])[0]["id"])
    body = {
        "observed_evidence": ["Synthetic evidence line"],
        "gaps": ["Synthetic gap line"],
        "follow_up_needed": True,
        "notes": "Synthetic human note",
    }
    created = client.post(
        f"{_URL}/questions/{question_id}/feedback",
        json=body,
        headers=_headers(seeded),
    )
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["interviewer_id"] == seeded["owner_a_id"]
    assert result["requirement_id"] == str(scenario.requirement_id)
    assert result["status"] == InterviewFeedbackStatus.SUBMITTED.value
    assert "score" not in result
    assert "decision" not in result
    assert "organization_id" not in result

    forged = client.post(
        f"{_URL}/questions/{question_id}/feedback",
        json={**body, "interviewer_id": seeded["owner_b_id"]},
        headers=_headers(seeded),
    )
    assert forged.status_code == 422, forged.text

    history = client.get(
        f"{_URL}/questions/{question_id}/feedback",
        params={"limit": 1, "offset": 0},
        headers=_headers(seeded),
    )
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == result["id"]

    feedback_audit = [
        entry.action
        for entry in list_resource_events(
            db, uuid.UUID(scenario.org_a), "interview_feedback", uuid.UUID(result["id"])
        )
    ]
    assert feedback_audit == ["interview.feedback_submitted"]
    assert (
        client.get(
            f"{_URL}/questions/{question_id}/feedback", headers=_headers(seeded, "b")
        ).status_code
        == 403
    )
