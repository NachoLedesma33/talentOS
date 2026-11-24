from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.pool import StaticPool

import app.audit.models  # noqa: F401
import app.candidates.models  # noqa: F401
import app.documents.models  # noqa: F401
import app.identity.models  # noqa: F401
import app.jobs.models  # noqa: F401
from app.agents.matching_analyst import PROMPT_VERSION
from app.applications.models import Application
from app.assessment import context as assessment_context
from app.assessment import service
from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)
from app.audit.service import list_resource_events
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
from app.identity.models import Membership, MembershipRole, Organization, User
from app.jobs.models import (
    Job,
    JobRequirement,
    JobVersion,
    RequirementCategory,
    RequirementImportance,
)

_QUOTE = "Skills: Python"
_MARKER = "SyntheticSkillMarker456"
_FOREIGN_MARKER = "ForeignSyntheticMarker789"


@dataclass(frozen=True)
class _Tenant:
    org: Organization
    user: User
    candidate: Candidate


@dataclass(frozen=True)
class _Scenario:
    tenant: _Tenant
    application: Application
    job: Job
    version: JobVersion
    requirement_ids: tuple[uuid.UUID, ...]
    document: Document
    extraction: DocumentExtraction
    field: ExtractedField


class _Provider:
    """Proveedor determinista controlado: cuenta llamadas y devuelve un dict."""

    def __init__(
        self,
        output: dict[str, object]
        | Callable[[dict[str, object]], dict[str, object]],
    ) -> None:
        self.output = output
        self.calls = 0
        self.contexts: list[dict[str, object]] = []

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: dict[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema
        self.calls += 1
        self.contexts.append(context)
        if callable(self.output):
            return self.output(context)
        return self.output

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
    org = Organization(name=f"Org {suffix}", slug=f"matching-org-{suffix}")
    user = User(
        email=f"owner-{suffix}-matching@example.test",
        password_hash="synthetic-hash",
        name="Synthetic Owner",
    )
    db.add_all([org, user])
    db.flush()
    db.add(
        Membership(
            organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER
        )
    )
    candidate = Candidate(
        organization_id=org.id,
        name="Synthetic Candidate",
        email=f"candidate-{suffix}-matching@example.test",
    )
    db.add(candidate)
    db.flush()
    return _Tenant(org, user, candidate)


def _snapshot(
    job: Job, items: Sequence[tuple[uuid.UUID, str]]
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
            for requirement_id, description in items
        ],
    }


def _document(
    db: DBSession,
    tenant: _Tenant,
    *,
    text: str,
    field_name: str,
    value: object,
    status: ExtractedFieldStatus,
    quote: str = _QUOTE,
    offset: int = 0,
) -> tuple[Document, DocumentExtraction, ExtractedField]:
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
    field = ExtractedField(
        extraction_id=extraction.id,
        field_name=ExtractedFieldName(field_name),
        value=value,
        status=status,
        evidence=[
            {
                "document_id": str(document.id),
                "page": 1,
                "quote": quote,
                "offset": offset,
            }
        ],
    )
    db.add(field)
    db.flush()
    return document, extraction, field


def _scenario(
    db: DBSession,
    tenant: _Tenant,
    *,
    descriptions: Sequence[str] = ("Synthetic skill requirement",),
    status: ExtractedFieldStatus = ExtractedFieldStatus.CONFIRMED,
    value: object = "Python",
) -> _Scenario:
    job = Job(
        organization_id=tenant.org.id,
        title="Synthetic role",
        owner_id=tenant.user.id,
    )
    db.add(job)
    db.flush()
    requirement_ids: list[uuid.UUID] = []
    for description in descriptions:
        requirement = JobRequirement(
            job_id=job.id,
            category=RequirementCategory.SKILL,
            description=description,
            importance=RequirementImportance.REQUIRED,
        )
        db.add(requirement)
        db.flush()
        requirement_ids.append(requirement.id)
    items = list(zip(requirement_ids, descriptions, strict=True))
    version = JobVersion(
        job_id=job.id, version=1, snapshot=_snapshot(job, items)
    )
    application = Application(
        organization_id=tenant.org.id,
        job_id=job.id,
        candidate_id=tenant.candidate.id,
    )
    db.add_all([version, application])
    db.flush()
    document, extraction, field = _document(
        db,
        tenant,
        text=f"{_QUOTE}\n",
        field_name="skills",
        value=value,
        status=status,
    )
    db.commit()
    return _Scenario(
        tenant, application, job, version, tuple(requirement_ids), document, extraction, field
    )


def _ref(
    document_id: uuid.UUID,
    *,
    field_name: str = "skills",
    page: int = 1,
    quote: str = _QUOTE,
    offset: int = 0,
) -> dict[str, object]:
    return {
        "document_id": str(document_id),
        "field_name": field_name,
        "page": page,
        "quote": quote,
        "offset": offset,
    }


def _result(
    requirement_id: uuid.UUID,
    status: RequirementEvaluationStatus,
    *,
    evidence_refs: Sequence[dict[str, object]] = (),
    explanation: str = "Synthetic explanation",
    limitations: Sequence[str] = (),
    review_required: bool = False,
) -> dict[str, object]:
    return {
        "requirement_id": str(requirement_id),
        "status": status.value,
        "evidence_refs": list(evidence_refs),
        "explanation": explanation,
        "limitations": list(limitations),
        "review_required": review_required,
    }


def _output(
    results: Sequence[dict[str, object]],
    *,
    strengths: Sequence[str] = (),
    gaps: Sequence[str] = (),
    questions: Sequence[str] = (),
    limitations: Sequence[str] = (),
    review_required: bool = False,
) -> dict[str, object]:
    return {
        "evaluations": list(results),
        "strengths": list(strengths),
        "gaps": list(gaps),
        "questions": list(questions),
        "limitations": list(limitations),
        "review_required": review_required,
        "model_version": "mock-model-v1",
        "prompt_version": PROMPT_VERSION,
    }


def _evaluations(db: DBSession, assessment: Assessment) -> list[RequirementEvaluation]:
    return list(
        db.scalars(
            select(RequirementEvaluation)
            .where(RequirementEvaluation.assessment_id == assessment.id)
            .order_by(RequirementEvaluation.requirement_id)
        ).all()
    )


def test_supported_requirement_keeps_verified_evidence(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(db, _tenant(db, "supported"))
    provider = _Provider(
        _output(
            [
                _result(
                    scenario.requirement_ids[0],
                    RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[_ref(scenario.document.id)],
                )
            ],
            strengths=["Synthetic strength"],
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    assessment = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )
    evaluations = _evaluations(db, assessment)

    assert assessment.status is AssessmentStatus.COMPLETED
    assert assessment.model_version == "mock-model-v1"
    assert assessment.prompt_version == PROMPT_VERSION
    assert len(evaluations) == 1
    assert evaluations[0].status is RequirementEvaluationStatus.SUPPORTED
    assert evaluations[0].evidence[0]["field_name"] == "skills"
    assert evaluations[0].evidence[0]["quote"] == _QUOTE
    assert evaluations[0].review_required is False
    assert assessment.summary["strengths"] == ["Synthetic strength"]
    events = list_resource_events(
        db, scenario.tenant.org.id, "assessment", assessment.id
    )
    assert [event.action for event in events] == ["assessment.created"]


def test_partial_evidence_remains_partial(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(db, _tenant(db, "partial"))
    provider = _Provider(
        _output(
            [
                _result(
                    scenario.requirement_ids[0],
                    RequirementEvaluationStatus.PARTIAL,
                    evidence_refs=[_ref(scenario.document.id)],
                )
            ]
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    assessment = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )

    assert _evaluations(db, assessment)[0].status is RequirementEvaluationStatus.PARTIAL
    assert assessment.status is AssessmentStatus.COMPLETED


def test_missing_evidence_is_not_found(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(db, _tenant(db, "not-found"))
    provider = _Provider(
        _output(
            [
                _result(
                    scenario.requirement_ids[0],
                    RequirementEvaluationStatus.NOT_FOUND,
                    explanation="No professional evidence found",
                )
            ],
            gaps=["Synthetic gap"],
            questions=["Synthetic question"],
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    assessment = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )
    evaluation = _evaluations(db, assessment)[0]

    assert evaluation.status is RequirementEvaluationStatus.NOT_FOUND
    assert evaluation.evidence == []
    assert evaluation.review_required is True
    assert assessment.status is AssessmentStatus.NEEDS_REVIEW
    assert assessment.summary["questions"] == ["Synthetic question"]


def test_conflicting_confirmed_fields_force_review(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = _tenant(db, "contradiction")
    scenario = _scenario(db, tenant, value="Python")
    other, _, _ = _document(
        db,
        tenant,
        text="Skills: Java\n",
        field_name="skills",
        value="Java",
        status=ExtractedFieldStatus.CORRECTED,
        quote="Skills: Java",
    )
    db.commit()
    provider = _Provider(
        _output(
            [
                _result(
                    scenario.requirement_ids[0],
                    RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[_ref(scenario.document.id)],
                )
            ]
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    assessment = service.run_assessment(
        db,
        organization_id=tenant.org.id,
        application_id=scenario.application.id,
        actor_id=tenant.user.id,
    )
    evaluation = _evaluations(db, assessment)[0]

    assert other.id != scenario.document.id
    assert evaluation.status is RequirementEvaluationStatus.NEEDS_REVIEW
    assert evaluation.evidence == []
    assert "conflicting_confirmed_fields" in evaluation.limitations
    assert assessment.status is AssessmentStatus.NEEDS_REVIEW


def test_unknown_evidence_reference_becomes_needs_review(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(db, _tenant(db, "bad-ref"))
    provider = _Provider(
        _output(
            [
                _result(
                    scenario.requirement_ids[0],
                    RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[_ref(uuid.uuid4())],
                )
            ]
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    assessment = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )
    evaluation = _evaluations(db, assessment)[0]

    assert evaluation.status is RequirementEvaluationStatus.NEEDS_REVIEW
    assert evaluation.evidence == []
    assert "invalid_evidence_dropped" in evaluation.limitations


def test_new_job_version_creates_a_separate_assessment(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(db, _tenant(db, "versions"))

    def _provider_output(context: dict[str, object]) -> dict[str, object]:
        requirements = context["requirements"]
        assert isinstance(requirements, list)
        return _output(
            [
                _result(
                    uuid.UUID(str(item["requirement_id"])),
                    RequirementEvaluationStatus.NOT_FOUND,
                )
                for item in requirements
                if isinstance(item, dict)
            ]
        )

    provider = _Provider(_provider_output)
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    first = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )

    new_requirement = JobRequirement(
        job_id=scenario.job.id,
        category=RequirementCategory.SKILL,
        description="Revised synthetic requirement",
        importance=RequirementImportance.REQUIRED,
    )
    db.add(new_requirement)
    db.flush()
    second_version = JobVersion(
        job_id=scenario.job.id,
        version=2,
        snapshot=_snapshot(
            scenario.job, [(new_requirement.id, new_requirement.description)]
        ),
    )
    db.add(second_version)
    db.commit()

    second = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )

    assert second.id != first.id
    assert first.job_version_id == scenario.version.id
    assert second.job_version_id == second_version.id
    assert [item.requirement_id for item in _evaluations(db, first)] == [
        scenario.requirement_ids[0]
    ]
    assert [item.requirement_id for item in _evaluations(db, second)] == [
        new_requirement.id
    ]
    assert db.scalar(select(func.count()).select_from(Assessment)) == 2


def test_repeated_assessment_is_idempotent(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(db, _tenant(db, "idempotent"))
    provider = _Provider(
        _output(
            [
                _result(
                    scenario.requirement_ids[0],
                    RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[_ref(scenario.document.id)],
                )
            ]
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    kwargs = {
        "organization_id": scenario.tenant.org.id,
        "application_id": scenario.application.id,
        "actor_id": scenario.tenant.user.id,
    }

    first = service.run_assessment(db, **kwargs)
    second = service.run_assessment(db, **kwargs)

    assert second.id == first.id
    assert provider.calls == 1
    assert db.scalar(select(func.count()).select_from(Assessment)) == 1
    assert db.scalar(select(func.count()).select_from(RequirementEvaluation)) == 1
    assert _evaluations(db, second)[0].status is RequirementEvaluationStatus.SUPPORTED


def test_cross_tenant_cannot_read_requirements_or_documents(
    db: DBSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_scenario = _scenario(db, _tenant(db, "owner"))
    outsider = _tenant(db, "outsider")
    db.commit()
    provider = _Provider(_output([]))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    seen_orgs: list[uuid.UUID] = []
    real_list_documents = assessment_context.list_documents

    def _spy_documents(
        session: DBSession,
        organization_id: uuid.UUID,
        candidate_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> object:
        seen_orgs.append(organization_id)
        return real_list_documents(
            session, organization_id, candidate_id=candidate_id, limit=limit, offset=offset
        )

    monkeypatch.setattr(assessment_context, "list_documents", _spy_documents)

    empty = assessment_context.build_context(
        db, outsider.org.id, owner_scenario.application.id
    )
    with pytest.raises(service.AssessmentDomainError) as exc:
        service.run_assessment(
            db,
            organization_id=outsider.org.id,
            application_id=owner_scenario.application.id,
            actor_id=outsider.user.id,
        )

    assert exc.value.code == "not_found"
    assert empty["requirements"] == []
    assert empty["candidate_id"] is None
    assert owner_scenario.tenant.org.id not in seen_orgs
    assert provider.calls == 0
    assert db.scalar(select(func.count()).select_from(Assessment)) == 0


def test_without_confirmed_fields_skips_provider(
    db: DBSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _scenario(
        db,
        _tenant(db, "unconfirmed"),
        status=ExtractedFieldStatus.EXTRACTED,
    )
    provider = _Provider(_output([]))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    assessment = service.run_assessment(
        db,
        organization_id=scenario.tenant.org.id,
        application_id=scenario.application.id,
        actor_id=scenario.tenant.user.id,
    )
    evaluation = _evaluations(db, assessment)[0]

    assert provider.calls == 0
    assert evaluation.status is RequirementEvaluationStatus.NOT_FOUND
    assert evaluation.evidence == []
    assert "no_confirmed_fields" in assessment.limitations
    assert assessment.model_version == service.DETERMINISTIC_MODEL_VERSION


def test_logs_exclude_cv_quotes_and_field_values(
    db: DBSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = _tenant(db, "logs")
    text = f"{_QUOTE} {_MARKER}\n"
    job = Job(
        organization_id=tenant.org.id, title="Synthetic role", owner_id=tenant.user.id
    )
    db.add(job)
    db.flush()
    requirement = JobRequirement(
        job_id=job.id,
        category=RequirementCategory.SKILL,
        description="Synthetic skill requirement",
        importance=RequirementImportance.REQUIRED,
    )
    db.add(requirement)
    db.flush()
    version = JobVersion(
        job_id=job.id,
        version=1,
        snapshot=_snapshot(job, [(requirement.id, requirement.description)]),
    )
    application = Application(
        organization_id=tenant.org.id,
        job_id=job.id,
        candidate_id=tenant.candidate.id,
    )
    db.add_all([version, application])
    db.flush()
    _, _, field = _document(
        db,
        tenant,
        text=text,
        field_name="skills",
        value=_MARKER,
        status=ExtractedFieldStatus.CONFIRMED,
        quote=_MARKER,
        offset=_QUOTE.find(_MARKER) + 2,
    )
    assert field.field_name is ExtractedFieldName.SKILLS
    db.commit()
    provider = _Provider(
        _output(
            [
                _result(
                    requirement.id,
                    RequirementEvaluationStatus.SUPPORTED,
                    evidence_refs=[
                        _ref(
                            uuid.UUID(str(field.evidence[0]["document_id"])),
                            quote=_MARKER,
                            offset=int(field.evidence[0]["offset"]),
                        )
                    ],
                    explanation=f"Synthetic explanation with {_MARKER}",
                )
            ]
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    caplog.set_level(logging.INFO)

    service.run_assessment(
        db,
        organization_id=tenant.org.id,
        application_id=application.id,
        actor_id=tenant.user.id,
    )

    assert "assessment.created" in caplog.text
    assert _MARKER not in caplog.text
    assert _QUOTE not in caplog.text
    assert "Synthetic explanation" not in caplog.text
    assert "Traceback" not in caplog.text
