from __future__ import annotations

import json
from collections.abc import Mapping

import pytest
from pydantic import BaseModel

from app.assessment.matching_schema import AssessmentOutput
from app.evaluation.extraction import evaluate_extraction
from app.evaluation.matching import evaluate_matching
from app.evaluation.report import (
    EvaluationSnapshot,
    build_snapshot,
    compare_snapshots,
    render_evaluation_report,
)
from app.llm.mock import MockLLMProvider


class _MatchingProvider:
    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del schema, context
        output = AssessmentOutput(
            evaluations=[],
            strengths=[],
            gaps=[],
            questions=[],
            limitations=[],
            review_required=False,
            model_version="evaluation-stub-v1",
            prompt_version=prompt_version,
        )
        return output.model_dump(mode="json")

    def generate_text(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> str:
        del prompt_version, context
        return ""

    def health_check(self) -> bool:
        return True

    def estimate_usage(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> dict[str, int]:
        del prompt_version, context
        return {"prompt_tokens": 1, "completion_tokens": 0}


def _snapshot() -> EvaluationSnapshot:
    return build_snapshot(
        extraction=evaluate_extraction(MockLLMProvider()),
        matching=evaluate_matching(_MatchingProvider()),
    )


def test_same_snapshot_has_no_regressions() -> None:
    snapshot = _snapshot()
    comparison = compare_snapshots(snapshot, snapshot)

    assert comparison.passed
    assert comparison.regressions == ()
    assert comparison.same_dataset
    assert comparison.same_extraction_prompt
    assert comparison.same_matching_prompt
    assert comparison.same_extraction_provider
    assert comparison.same_matching_provider
    assert all(metric.delta == 0 for metric in comparison.metrics)


def test_lower_extraction_accuracy_is_reported_as_regression() -> None:
    snapshot = _snapshot()
    candidate = snapshot.model_copy(
        update={
            "extraction": snapshot.extraction.model_copy(
                update={
                    "field_matches": snapshot.extraction.field_matches - 1,
                    "provider": "other-provider",
                }
            )
        }
    )

    comparison = compare_snapshots(snapshot, candidate)

    assert not comparison.passed
    assert comparison.regressions == ("extraction.field_matches",)
    assert not comparison.same_extraction_provider
    assert comparison.same_matching_provider


def test_rendered_report_is_json_and_carries_no_pii() -> None:
    snapshot = _snapshot()
    rendered = render_evaluation_report(snapshot, snapshot)
    payload = json.loads(rendered)

    assert payload["snapshot"]["dataset_version"] == snapshot.dataset_version
    assert payload["comparison"]["passed"] is True
    assert "Synthetic" not in rendered
    assert "@example.test" not in rendered


def test_build_snapshot_rejects_dataset_mismatch() -> None:
    snapshot = _snapshot()
    other_matching = snapshot.matching.model_copy(update={"dataset_version": "9.9.9"})

    with pytest.raises(ValueError, match="dataset_version_mismatch"):
        build_snapshot(extraction=snapshot.extraction, matching=other_matching)
