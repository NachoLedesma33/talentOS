from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.cv_analyst import PROMPT_VERSION, AnalysisContext, PageContext
from app.agents.extraction_schema import EvidenceRef, ExtractedProfile
from app.evaluation.dataset import DATASET_CASES, DATASET_VERSION, DatasetCase
from app.llm.provider import LLMProvider, ProviderError

_EVALUATION_ORGANIZATION = uuid.uuid5(
    uuid.NAMESPACE_URL, "talentos-evaluation-organization"
)


class ExtractionCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    schema_valid: bool
    error_code: str | None = None
    field_total: int
    field_matches: int
    evidence_total: int
    evidence_valid: int
    expected_evidence_total: int
    expected_evidence_matched: int
    prompt_injection_match: bool
    review_required_match: bool
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class ExtractionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str
    prompt_version: str
    provider: str
    cases: tuple[ExtractionCaseResult, ...]
    schema_valid_cases: int
    field_total: int
    field_matches: int
    evidence_total: int
    evidence_valid: int
    expected_evidence_total: int
    expected_evidence_matched: int
    prompt_injection_matches: int
    review_required_matches: int
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


def _failed_case(
    case_id: str, latency_ms: float, error_code: str
) -> ExtractionCaseResult:
    return ExtractionCaseResult(
        case_id=case_id,
        schema_valid=False,
        error_code=error_code,
        field_total=0,
        field_matches=0,
        evidence_total=0,
        evidence_valid=0,
        expected_evidence_total=0,
        expected_evidence_matched=0,
        prompt_injection_match=False,
        review_required_match=False,
        latency_ms=latency_ms,
        prompt_tokens=0,
        completion_tokens=0,
    )


def _evaluate_case(
    provider: LLMProvider,
    case: DatasetCase,
    *,
    prompt_version: str,
) -> ExtractionCaseResult:
    document_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{DATASET_VERSION}:extraction:{case.id}"
    )
    context = AnalysisContext(
        document_id=document_id,
        organization_id=_EVALUATION_ORGANIZATION,
        pages=[PageContext(page=1, text=case.text)],
        prompt_version=prompt_version,
    ).as_provider_mapping()

    started = time.perf_counter()
    try:
        raw = provider.generate_structured_output(
            prompt_version, ExtractedProfile, context
        )
    except (ProviderError, TypeError, ValueError):
        latency_ms = (time.perf_counter() - started) * 1000
        return _failed_case(case.id, latency_ms, "provider_failed")

    try:
        profile = ExtractedProfile.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        latency_ms = (time.perf_counter() - started) * 1000
        return _failed_case(case.id, latency_ms, "invalid_provider_output")

    if profile.prompt_version != prompt_version:
        latency_ms = (time.perf_counter() - started) * 1000
        return _failed_case(case.id, latency_ms, "prompt_version_mismatch")

    usage: dict[str, int] = {}
    try:
        usage = provider.estimate_usage(prompt_version, context)
    except (ProviderError, TypeError, ValueError):
        pass
    latency_ms = (time.perf_counter() - started) * 1000

    actual_fields = {field.field_name: field for field in profile.fields}
    field_matches = 0
    for expected in case.expected_fields:
        actual = actual_fields.get(expected.field_name)
        if actual is None or actual.status is not expected.status:
            continue
        if expected.value is None:
            if actual.value is None:
                field_matches += 1
        elif actual.value == expected.value:
            field_matches += 1

    refs: list[EvidenceRef] = list(profile.prompt_injection_evidence)
    for field in profile.fields:
        refs.extend(field.evidence_refs)
    evidence_valid = sum(
        ref.document_id == document_id
        and ref.page == 1
        and ref.quote in case.text
        and (ref.offset is None or ref.offset == case.text.find(ref.quote))
        for ref in refs
    )
    actual_quotes = {ref.quote for ref in refs}
    expected_quotes = [
        quote for field in case.expected_fields for quote in field.quotes
    ]
    expected_quotes.extend(case.expected_prompt_injection_quotes)
    expected_evidence_matched = sum(
        quote in actual_quotes for quote in expected_quotes
    )

    return ExtractionCaseResult(
        case_id=case.id,
        schema_valid=True,
        field_total=len(case.expected_fields),
        field_matches=field_matches,
        evidence_total=len(refs),
        evidence_valid=evidence_valid,
        expected_evidence_total=len(expected_quotes),
        expected_evidence_matched=expected_evidence_matched,
        prompt_injection_match=(
            profile.prompt_injection_detected == case.prompt_injection_detected
        ),
        review_required_match=(profile.review_required == case.review_required),
        latency_ms=round(latency_ms, 3),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )


def evaluate_extraction(
    provider: LLMProvider,
    *,
    prompt_version: str = PROMPT_VERSION,
    cases: Sequence[DatasetCase] = DATASET_CASES,
    provider_label: str | None = None,
) -> ExtractionReport:
    results = tuple(
        _evaluate_case(provider, case, prompt_version=prompt_version) for case in cases
    )
    return ExtractionReport(
        dataset_version=DATASET_VERSION,
        prompt_version=prompt_version,
        provider=provider_label or type(provider).__name__,
        cases=results,
        schema_valid_cases=sum(case.schema_valid for case in results),
        field_total=sum(case.field_total for case in results),
        field_matches=sum(case.field_matches for case in results),
        evidence_total=sum(case.evidence_total for case in results),
        evidence_valid=sum(case.evidence_valid for case in results),
        expected_evidence_total=sum(case.expected_evidence_total for case in results),
        expected_evidence_matched=sum(
            case.expected_evidence_matched for case in results
        ),
        prompt_injection_matches=sum(case.prompt_injection_match for case in results),
        review_required_matches=sum(case.review_required_match for case in results),
        latency_ms=round(sum(case.latency_ms for case in results), 3),
        prompt_tokens=sum(case.prompt_tokens for case in results),
        completion_tokens=sum(case.completion_tokens for case in results),
    )
