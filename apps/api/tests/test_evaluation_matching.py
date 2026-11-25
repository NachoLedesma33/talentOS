from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel

from app.assessment.matching_schema import AssessmentOutput, MatchingEvidenceRef
from app.assessment.models import RequirementEvaluationStatus
from app.evaluation.dataset import DATASET_CASES, DATASET_VERSION
from app.evaluation.matching import evaluate_matching


class _MatchingProvider:
    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del schema
        requirements = cast(list[dict[str, object]], context["requirements"])
        untrusted = cast(dict[str, object], context["untrusted_candidate_data"])
        confirmed = cast(list[dict[str, object]], untrusted["confirmed_fields"])
        missing = cast(list[str], untrusted["missing_fields"])
        contradictions = cast(list[str], untrusted["contradictions"])
        injection = cast(bool, untrusted["prompt_injection_suspected"])
        document_id = uuid.UUID(str(context["document_id"]))

        values: list[tuple[str, str]] = []
        for field in confirmed:
            value = field["value"]
            if isinstance(value, (list, tuple)):
                text = ", ".join(str(item) for item in value)
            else:
                text = str(value)
            quotes = cast(list[str], field["quotes"])
            if text and quotes:
                values.append((text.casefold(), quotes[0]))

        evaluations = []
        for requirement in requirements:
            requirement_id = uuid.UUID(str(requirement["requirement_id"]))
            description = str(requirement["description"])
            evidence = next(
                (quote for value, quote in values if description.casefold() in value),
                None,
            )
            if evidence is None:
                evaluation_status = RequirementEvaluationStatus.NOT_FOUND
                evidence_refs = []
            else:
                evaluation_status = RequirementEvaluationStatus.SUPPORTED
                evidence_refs = [
                    MatchingEvidenceRef(
                        document_id=document_id,
                        field_name="skills",
                        page=1,
                        quote=evidence,
                    )
                ]
            evaluations.append(
                {
                    "requirement_id": requirement_id,
                    "status": evaluation_status,
                    "evidence_refs": [ref.model_dump() for ref in evidence_refs],
                    "explanation": "confirmed in synthetic dataset",
                    "limitations": [],
                    "review_required": False,
                }
            )

        output = AssessmentOutput(
            evaluations=evaluations,
            strengths=[],
            gaps=[],
            questions=[],
            limitations=[],
            review_required=bool(contradictions or missing or injection),
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
        del prompt_version
        return {"prompt_tokens": max(1, len(str(context)) // 4), "completion_tokens": 0}


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


def test_matching_evaluation_reports_consistency_without_pii() -> None:
    report = evaluate_matching(_MatchingProvider())

    assert report.dataset_version == DATASET_VERSION
    assert report.prompt_version == "matching-v1"
    assert report.provider == "_MatchingProvider"
    assert len(report.cases) == len(DATASET_CASES)
    assert report.schema_valid_cases == len(DATASET_CASES)
    assert report.requirements_total == 5
    assert report.status_matches == 5
    assert report.evidence_total == 3
    assert report.evidence_valid == 3
    assert report.unexpected_requirements == 0
    assert report.positive_without_evidence == 0
    assert report.not_found_with_evidence == 0
    assert report.review_required_matches == len(DATASET_CASES)
    assert all(case.model_version == "evaluation-stub-v1" for case in report.cases)

    serialized = json.dumps(report.model_dump())
    assert "Synthetic" not in serialized
    assert "@example.test" not in serialized


def test_invalid_matching_output_is_counted_without_payload() -> None:
    report = evaluate_matching(_BadProvider(), cases=DATASET_CASES[:1])

    assert report.schema_valid_cases == 0
    assert report.cases[0].error_code == "invalid_provider_output"
    assert report.cases[0].requirements_total == 0
