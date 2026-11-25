from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from app.evaluation.extraction import ExtractionReport
from app.evaluation.matching import MatchingReport


class EvaluationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str
    extraction: ExtractionReport
    matching: MatchingReport


class RegressionMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    baseline: float
    candidate: float
    delta: float
    higher_is_better: bool
    regressed: bool


class RegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_dataset_version: str
    candidate_dataset_version: str
    same_dataset: bool
    same_extraction_prompt: bool
    same_matching_prompt: bool
    same_extraction_provider: bool
    same_matching_provider: bool
    metrics: tuple[RegressionMetric, ...]
    regressions: tuple[str, ...]
    passed: bool


_METRICS: tuple[tuple[str, Callable[[EvaluationSnapshot], float], bool], ...] = (
    (
        "extraction.schema_valid_cases",
        lambda snapshot: snapshot.extraction.schema_valid_cases,
        True,
    ),
    ("extraction.field_matches", lambda snapshot: snapshot.extraction.field_matches, True),
    (
        "extraction.evidence_valid",
        lambda snapshot: snapshot.extraction.evidence_valid,
        True,
    ),
    (
        "extraction.expected_evidence_matched",
        lambda snapshot: snapshot.extraction.expected_evidence_matched,
        True,
    ),
    (
        "extraction.prompt_injection_matches",
        lambda snapshot: snapshot.extraction.prompt_injection_matches,
        True,
    ),
    (
        "extraction.prompt_tokens",
        lambda snapshot: snapshot.extraction.prompt_tokens,
        False,
    ),
    ("matching.schema_valid_cases", lambda snapshot: snapshot.matching.schema_valid_cases, True),
    ("matching.status_matches", lambda snapshot: snapshot.matching.status_matches, True),
    ("matching.evidence_valid", lambda snapshot: snapshot.matching.evidence_valid, True),
    (
        "matching.unexpected_requirements",
        lambda snapshot: snapshot.matching.unexpected_requirements,
        False,
    ),
    (
        "matching.positive_without_evidence",
        lambda snapshot: snapshot.matching.positive_without_evidence,
        False,
    ),
    (
        "matching.not_found_with_evidence",
        lambda snapshot: snapshot.matching.not_found_with_evidence,
        False,
    ),
    (
        "matching.review_required_matches",
        lambda snapshot: snapshot.matching.review_required_matches,
        True,
    ),
    (
        "extraction.latency_ms",
        lambda snapshot: snapshot.extraction.latency_ms,
        False,
    ),
    ("matching.latency_ms", lambda snapshot: snapshot.matching.latency_ms, False),
)


def build_snapshot(
    *, extraction: ExtractionReport, matching: MatchingReport
) -> EvaluationSnapshot:
    if extraction.dataset_version != matching.dataset_version:
        raise ValueError("dataset_version_mismatch")
    return EvaluationSnapshot(
        dataset_version=extraction.dataset_version,
        extraction=extraction,
        matching=matching,
    )


def compare_snapshots(
    baseline: EvaluationSnapshot, candidate: EvaluationSnapshot
) -> RegressionReport:
    metrics: list[RegressionMetric] = []
    for name, value, higher_is_better in _METRICS:
        baseline_value = value(baseline)
        candidate_value = value(candidate)
        delta = candidate_value - baseline_value
        regressed = (
            delta < 0 if higher_is_better else delta > 0
        )
        metrics.append(
            RegressionMetric(
                name=name,
                baseline=baseline_value,
                candidate=candidate_value,
                delta=round(delta, 3),
                higher_is_better=higher_is_better,
                regressed=regressed,
            )
        )
    regressions = tuple(metric.name for metric in metrics if metric.regressed)
    return RegressionReport(
        baseline_dataset_version=baseline.dataset_version,
        candidate_dataset_version=candidate.dataset_version,
        same_dataset=baseline.dataset_version == candidate.dataset_version,
        same_extraction_prompt=(
            baseline.extraction.prompt_version == candidate.extraction.prompt_version
        ),
        same_matching_prompt=(
            baseline.matching.prompt_version == candidate.matching.prompt_version
        ),
        same_extraction_provider=(
            baseline.extraction.provider == candidate.extraction.provider
        ),
        same_matching_provider=(
            baseline.matching.provider == candidate.matching.provider
        ),
        metrics=tuple(metrics),
        regressions=regressions,
        passed=not regressions,
    )


def render_evaluation_report(
    snapshot: EvaluationSnapshot, baseline: EvaluationSnapshot | None = None
) -> str:
    payload: dict[str, object] = {"snapshot": snapshot.model_dump(mode="json")}
    if baseline is not None:
        payload["comparison"] = compare_snapshots(baseline, snapshot).model_dump(
            mode="json"
        )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
