from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.extraction_schema import FieldStatus
from app.agents.matching_analyst import PROMPT_VERSION
from app.assessment.matching_schema import AssessmentOutput
from app.assessment.models import RequirementEvaluationStatus
from app.evaluation.dataset import DATASET_CASES, DATASET_VERSION, DatasetCase
from app.llm.provider import LLMProvider, ProviderError

_EVALUATION_ORGANIZATION = uuid.uuid5(uuid.NAMESPACE_URL, "talentos-evaluation-organization")


class MatchingCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    schema_valid: bool
    error_code: str | None = None
    model_version: str | None = None
    requirements_total: int
    status_matches: int
    unexpected_requirements: int
    evidence_total: int
    evidence_valid: int
    positive_without_evidence: int
    not_found_with_evidence: int
    review_required_match: bool
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class MatchingReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str
    prompt_version: str
    provider: str
    cases: tuple[MatchingCaseResult, ...]
    schema_valid_cases: int
    requirements_total: int
    status_matches: int
    unexpected_requirements: int
    evidence_total: int
    evidence_valid: int
    positive_without_evidence: int
    not_found_with_evidence: int
    review_required_matches: int
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


def _failed_case(
    case_id: str, latency_ms: float, error_code: str
) -> MatchingCaseResult:
    return MatchingCaseResult(
        case_id=case_id,
        schema_valid=False,
        error_code=error_code,
        requirements_total=0,
        status_matches=0,
        unexpected_requirements=0,
        evidence_total=0,
        evidence_valid=0,
        positive_without_evidence=0,
        not_found_with_evidence=0,
        review_required_match=False,
        latency_ms=latency_ms,
        prompt_tokens=0,
        completion_tokens=0,
    )


def _requirement_id(case: DatasetCase, description: str) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"{DATASET_VERSION}:matching:{case.id}:{description}"
    )


def _confirmed_fields(case: DatasetCase) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    for expected in case.expected_fields:
        if expected.status is not FieldStatus.EXTRACTED:
            continue
        fields.append(
            {
                "field_name": expected.field_name.value,
                "value": expected.value,
                "quotes": list(expected.quotes),
            }
        )
    return fields


def _build_context(
    case: DatasetCase, document_id: uuid.UUID
) -> dict[str, object]:
    requirements = [
        {
            "requirement_id": str(_requirement_id(case, description)),
            "description": description,
            "category": "skill",
            "importance": "required",
            "expected_level": None,
        }
        for description in case.job_requirements
    ]
    missing_fields = [
        expected.field_name.value
        for expected in case.expected_fields
        if expected.status is FieldStatus.MISSING
    ]
    needs_review_fields = [
        expected.field_name.value
        for expected in case.expected_fields
        if expected.status is FieldStatus.NEEDS_REVIEW
    ]
    contradictions = [
        quote
        for expected in case.expected_fields
        if expected.status is FieldStatus.NEEDS_REVIEW
        for quote in expected.quotes
    ]
    contradictions.extend(case.expected_prompt_injection_quotes)
    return {
        "organization_id": str(_EVALUATION_ORGANIZATION),
        "job_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_VERSION}:job:{case.id}")),
        "job_version_id": str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_VERSION}:version:{case.id}")
        ),
        "document_id": str(document_id),
        "requirements": requirements,
        "untrusted_candidate_data": {
            "confirmed_fields": _confirmed_fields(case),
            "missing_fields": missing_fields,
            "needs_review_fields": needs_review_fields,
            "contradictions": contradictions,
            "prompt_injection_suspected": case.prompt_injection_detected,
        },
    }


def _expected_status(case: DatasetCase, description: str) -> RequirementEvaluationStatus:
    if description in case.expected_unmatched_requirements:
        return RequirementEvaluationStatus.NOT_FOUND
    if description.casefold() in case.text.casefold():
        return RequirementEvaluationStatus.SUPPORTED
    return RequirementEvaluationStatus.NEEDS_REVIEW


def _evaluate_case(
    provider: LLMProvider,
    case: DatasetCase,
    *,
    prompt_version: str,
) -> MatchingCaseResult:
    document_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_VERSION}:matching:{case.id}")
    context = _build_context(case, document_id)

    started = time.perf_counter()
    try:
        raw = provider.generate_structured_output(
            prompt_version, AssessmentOutput, context
        )
    except (ProviderError, TypeError, ValueError):
        latency_ms = (time.perf_counter() - started) * 1000
        return _failed_case(case.id, latency_ms, "provider_failed")

    try:
        output = AssessmentOutput.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        latency_ms = (time.perf_counter() - started) * 1000
        return _failed_case(case.id, latency_ms, "invalid_provider_output")

    if output.prompt_version != prompt_version:
        latency_ms = (time.perf_counter() - started) * 1000
        return _failed_case(case.id, latency_ms, "prompt_version_mismatch")

    usage: dict[str, int] = {}
    try:
        usage = provider.estimate_usage(prompt_version, context)
    except (ProviderError, TypeError, ValueError):
        pass
    latency_ms = (time.perf_counter() - started) * 1000

    expected_statuses = {
        _requirement_id(case, description): _expected_status(case, description)
        for description in case.job_requirements
    }
    matched: set[uuid.UUID] = set()
    unexpected_requirements = 0
    refs = []
    positive_without_evidence = 0
    not_found_with_evidence = 0
    for evaluation in output.evaluations:
        expected = expected_statuses.get(evaluation.requirement_id)
        if expected is None:
            unexpected_requirements += 1
        elif evaluation.status is expected:
            matched.add(evaluation.requirement_id)
        refs.extend(evaluation.evidence_refs)
        if (
            evaluation.status
            in {RequirementEvaluationStatus.SUPPORTED, RequirementEvaluationStatus.PARTIAL}
            and not evaluation.evidence_refs
        ):
            positive_without_evidence += 1
        if (
            evaluation.status is RequirementEvaluationStatus.NOT_FOUND
            and evaluation.evidence_refs
        ):
            not_found_with_evidence += 1

    evidence_valid = sum(
        ref.document_id == document_id
        and ref.page == 1
        and ref.quote in case.text
        and (ref.offset is None or ref.offset == case.text.find(ref.quote))
        for ref in refs
    )
    expected_review = case.review_required or case.prompt_injection_detected

    return MatchingCaseResult(
        case_id=case.id,
        schema_valid=True,
        model_version=output.model_version,
        requirements_total=len(expected_statuses),
        status_matches=len(matched),
        unexpected_requirements=unexpected_requirements,
        evidence_total=len(refs),
        evidence_valid=evidence_valid,
        positive_without_evidence=positive_without_evidence,
        not_found_with_evidence=not_found_with_evidence,
        review_required_match=(output.review_required == expected_review),
        latency_ms=round(latency_ms, 3),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )


def evaluate_matching(
    provider: LLMProvider,
    *,
    prompt_version: str = PROMPT_VERSION,
    cases: Sequence[DatasetCase] = DATASET_CASES,
    provider_label: str | None = None,
) -> MatchingReport:
    results = tuple(
        _evaluate_case(provider, case, prompt_version=prompt_version) for case in cases
    )
    return MatchingReport(
        dataset_version=DATASET_VERSION,
        prompt_version=prompt_version,
        provider=provider_label or type(provider).__name__,
        cases=results,
        schema_valid_cases=sum(case.schema_valid for case in results),
        requirements_total=sum(case.requirements_total for case in results),
        status_matches=sum(case.status_matches for case in results),
        unexpected_requirements=sum(case.unexpected_requirements for case in results),
        evidence_total=sum(case.evidence_total for case in results),
        evidence_valid=sum(case.evidence_valid for case in results),
        positive_without_evidence=sum(
            case.positive_without_evidence for case in results
        ),
        not_found_with_evidence=sum(case.not_found_with_evidence for case in results),
        review_required_matches=sum(case.review_required_match for case in results),
        latency_ms=round(sum(case.latency_ms for case in results), 3),
        prompt_tokens=sum(case.prompt_tokens for case in results),
        completion_tokens=sum(case.completion_tokens for case in results),
    )
