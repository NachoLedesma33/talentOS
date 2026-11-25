from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import BaseModel

from app.evaluation.dataset import DATASET_CASES, DATASET_VERSION
from app.evaluation.extraction import evaluate_extraction
from app.llm.mock import MockLLMProvider


class _BadProvider:
    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del prompt_version, schema, context
        return {"unexpected": True}

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


def test_mock_provider_evaluation_reports_metrics_without_pii() -> None:
    report = evaluate_extraction(MockLLMProvider())

    assert report.dataset_version == DATASET_VERSION
    assert report.prompt_version == "cv-extraction-v1"
    assert report.provider == "MockLLMProvider"
    assert len(report.cases) == len(DATASET_CASES)
    assert report.schema_valid_cases == len(DATASET_CASES)
    assert report.evidence_total == report.evidence_valid
    assert report.prompt_injection_matches == len(DATASET_CASES)
    assert report.field_matches < report.field_total
    assert report.prompt_tokens > 0
    assert report.completion_tokens == 0

    cases = {case.case_id: case for case in report.cases}
    assert cases["complete-pdf"].field_matches == cases["complete-pdf"].field_total
    assert cases["ambiguous-experience-pdf"].field_matches == 0
    assert cases["prompt-injection-docx"].prompt_injection_match

    serialized = json.dumps(report.model_dump())
    assert "Synthetic" not in serialized
    assert "@example.test" not in serialized


def test_invalid_provider_output_is_counted_without_payload() -> None:
    report = evaluate_extraction(_BadProvider(), cases=DATASET_CASES[:1])

    assert report.schema_valid_cases == 0
    assert report.cases[0].error_code == "invalid_provider_output"
    assert report.cases[0].field_total == 0
    assert report.cases[0].evidence_total == 0
