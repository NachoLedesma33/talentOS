from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.agents.matching_analyst as matching_analyst
import app.assessment.models  # noqa: F401
import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents.matching_analyst import (
    AGENT_ID,
    AGENT_VERSION,
    MAX_PROMPT_CHARS,
    PROMPT_VERSION,
    TOOLS_AUTHORIZED,
    AgentToolError,
    build_prompt,
    get_candidate_profile,
    get_confirmed_document_text,
    get_job_requirements,
)
from app.applications.models import Application
from app.assessment.matching_schema import AssessmentOutput, MatchingResult
from app.assessment.models import RequirementEvaluationStatus
from app.candidates.models import Candidate
from app.db.base import Base
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
from app.identity.models import Organization, User
from app.jobs.models import (
    Job,
    JobRequirement,
    JobVersion,
    RequirementCategory,
    RequirementImportance,
)

_QUOTE = "Skills: Python"
_FULL_CV_MARKER = "FullCvMarkerShouldNeverTravel"
_UNCONFIRMED_MARKER = "UnconfirmedMarkerShouldNotTravel"


@dataclass(frozen=True)
class _Tenant:
    org: Organization
    user: User
    candidate: Candidate


@dataclass(frozen=True)
class _Scenario:
    tenant: _Tenant
    outsider: _Tenant
    application: Application
    requirement_ids: tuple[uuid.UUID, ...]
    document: Document


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


def _tenant(db: DBSession, suffix: str) -> _Tenant:
    org = Organization(name=f"Org {suffix}", slug=f"matching-tools-org-{suffix}")
    user = User(
        email=f"owner-{suffix}-matching-tools@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Owner",
    )
    db.add_all([org, user])
    db.flush()
    candidate = Candidate(
        organization_id=org.id,
        name="Synthetic Candidate",
        email=f"candidate-{suffix}-matching-tools@example.test",
    )
    db.add(candidate)
    db.flush()
    return _Tenant(org, user, candidate)


def _snapshot(
    job: Job, requirements: Sequence[tuple[uuid.UUID, str]]
) -> dict[str, object]:
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
            for requirement_id, description in requirements
        ],
    }


def _requirement(db: DBSession, job: Job, description: str) -> JobRequirement:
    requirement = JobRequirement(
        job_id=job.id,
        category=RequirementCategory.SKILL,
        description=description,
        importance=RequirementImportance.REQUIRED,
    )
    db.add(requirement)
    db.flush()
    return requirement


def _field(
    db: DBSession,
    extraction_id: uuid.UUID,
    *,
    field_name: ExtractedFieldName,
    value: object,
    status: ExtractedFieldStatus,
    quote: str | None = None,
    document_id: uuid.UUID | None = None,
) -> ExtractedField:
    evidence: list[dict[str, object]] = []
    if quote is not None and document_id is not None:
        evidence.append(
            {
                "document_id": str(document_id),
                "page": 1,
                "quote": quote,
                "offset": 0,
            }
        )
    field = ExtractedField(
        extraction_id=extraction_id,
        field_name=field_name,
        value=value,
        status=status,
        evidence=evidence,
    )
    db.add(field)
    db.flush()
    return field


@pytest.fixture
def scenario(db: DBSession) -> _Scenario:
    tenant = _tenant(db, "owner")
    outsider = _tenant(db, "outsider")
    job = Job(
        organization_id=tenant.org.id,
        title="Synthetic role",
        owner_id=tenant.user.id,
    )
    db.add(job)
    db.flush()
    first = _requirement(db, job, "Synthetic primary requirement")
    second = _requirement(db, job, "Synthetic revised requirement")
    db.add_all(
        [
            JobVersion(
                job_id=job.id,
                version=1,
                snapshot=_snapshot(job, [(first.id, first.description)]),
            ),
            JobVersion(
                job_id=job.id,
                version=2,
                snapshot=_snapshot(
                    job,
                    [
                        (first.id, first.description),
                        (second.id, second.description),
                    ],
                ),
            ),
        ]
    )
    _requirement(db, job, "Synthetic mutable-only requirement")
    application = Application(
        organization_id=tenant.org.id,
        job_id=job.id,
        candidate_id=tenant.candidate.id,
    )
    db.add(application)
    db.flush()

    text = f"{_QUOTE}\n{_FULL_CV_MARKER}\n{_UNCONFIRMED_MARKER}\n"
    document = Document(
        organization_id=tenant.org.id,
        candidate_id=tenant.candidate.id,
        uploaded_by=tenant.user.id,
        original_filename="synthetic-cv.pdf",
        internal_name=uuid.uuid4().hex,
        content_type="application/pdf",
        extension=".pdf",
        size_bytes=len(text.encode()),
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
        pages=[{"page": 1, "text": text, "start_offset": 0, "end_offset": len(text)}],
    )
    db.add(extraction)
    db.flush()
    _field(
        db,
        extraction.id,
        field_name=ExtractedFieldName.SKILLS,
        value="Python",
        status=ExtractedFieldStatus.CONFIRMED,
        quote=_QUOTE,
        document_id=document.id,
    )
    _field(
        db,
        extraction.id,
        field_name=ExtractedFieldName.NAME,
        value=_UNCONFIRMED_MARKER,
        status=ExtractedFieldStatus.EXTRACTED,
    )
    db.commit()
    return _Scenario(tenant, outsider, application, (first.id, second.id), document)


def test_contract_constants_and_output_schema() -> None:
    assert AGENT_ID == "matching_analyst"
    assert AGENT_VERSION == "1.0.0"
    assert PROMPT_VERSION == "matching-v1"
    assert TOOLS_AUTHORIZED == (
        "get_job_requirements",
        "get_candidate_profile",
        "get_confirmed_document_text",
    )
    with pytest.raises(ValidationError):
        MatchingResult.model_validate(
            {
                "requirement_id": str(uuid.uuid4()),
                "status": RequirementEvaluationStatus.NOT_FOUND.value,
                "explanation": "Synthetic",
                "score": 0.9,
            }
        )
    with pytest.raises(ValidationError):
        AssessmentOutput.model_validate(
            {"model_version": "mock", "prompt_version": PROMPT_VERSION, "score": 0.9}
        )


def test_requirements_tool_uses_latest_snapshot_not_mutable_rows(
    db: DBSession, scenario: _Scenario
) -> None:
    result = get_job_requirements(db, scenario.tenant.org.id, scenario.application.id)
    requirements = list(result["requirements"])

    assert result["job_version_id"] is not None
    assert [item["requirement_id"] for item in requirements] == [
        str(scenario.requirement_ids[0]),
        str(scenario.requirement_ids[1]),
    ]
    mutable = select(JobRequirement).where(
        JobRequirement.description.contains("mutable-only")
    )
    assert db.scalar(mutable) is not None
    assert all("mutable-only" not in str(item["description"]) for item in requirements)


def test_candidate_profile_includes_only_confirmed_fields_and_bounded_evidence(
    db: DBSession, scenario: _Scenario
) -> None:
    result = get_candidate_profile(db, scenario.tenant.org.id, scenario.application.id)
    fields = list(result["fields"])
    evidence = list(result["evidence"])

    assert [item["field_name"] for item in fields] == ["skills"]
    assert fields[0]["value"] == "Python"
    assert evidence == [
        {
            "document_id": str(scenario.document.id),
            "field_name": "skills",
            "page": 1,
            "quote": _QUOTE,
            "offset": 0,
        }
    ]
    assert result["contradictions"] == []
    assert _FULL_CV_MARKER not in str(result)
    assert _UNCONFIRMED_MARKER not in str(result)


def test_confirmed_document_text_returns_quotes_not_full_cv(
    db: DBSession, scenario: _Scenario
) -> None:
    result = get_confirmed_document_text(
        db, scenario.tenant.org.id, scenario.application.id, scenario.document.id
    )
    quotes = list(result["quotes"])

    assert len(quotes) == 1
    assert quotes[0]["quote"] == _QUOTE
    assert _FULL_CV_MARKER not in str(result)
    assert _UNCONFIRMED_MARKER not in str(result)


def test_tools_reject_foreign_tenant(db: DBSession, scenario: _Scenario) -> None:
    outsider = scenario.outsider.org.id

    with pytest.raises(AgentToolError) as requirements_error:
        get_job_requirements(db, outsider, scenario.application.id)
    with pytest.raises(AgentToolError) as profile_error:
        get_candidate_profile(db, outsider, scenario.application.id)
    with pytest.raises(AgentToolError) as text_error:
        get_confirmed_document_text(
            db, outsider, scenario.application.id, scenario.document.id
        )

    assert requirements_error.value.code == "organization_mismatch"
    assert profile_error.value.code == "organization_mismatch"
    assert text_error.value.code == "organization_mismatch"


def test_tool_rejects_malformed_ids(db: DBSession, scenario: _Scenario) -> None:
    with pytest.raises(AgentToolError) as exc:
        get_candidate_profile(db, "not-a-uuid", scenario.application.id)

    assert exc.value.code == "invalid_context"


def test_prompt_delimits_untrusted_data_and_is_bounded(
    db: DBSession, scenario: _Scenario
) -> None:
    context = get_candidate_profile(db, scenario.tenant.org.id, scenario.application.id)
    prompt = build_prompt(context)

    assert "<untrusted_candidate_data>" in prompt
    assert "</untrusted_candidate_data>" in prompt
    assert "produzcas score" in prompt
    assert _FULL_CV_MARKER not in prompt
    assert len(build_prompt({"payload": "Synthetic" * MAX_PROMPT_CHARS})) <= (
        MAX_PROMPT_CHARS + len(matching_analyst.PROMPT_TEMPLATE)
    )
