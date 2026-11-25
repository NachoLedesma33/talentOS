from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from typing import cast

import pytest
from pydantic import BaseModel

from app.evaluation.dataset import DATASET_CASES, DATASET_VERSION
from app.evaluation.simulation import (
    SimulationScenario,
    SimulationStatus,
    simulate_dataset,
)
from app.llm.provider import ProviderError

_CASES = DATASET_CASES[:2]


def _valid_output(prompt_version: str) -> dict[str, object]:
    return {
        "prompt_version": prompt_version,
        "fields": [],
        "limitations": ["synthetic_simulation"],
        "review_required": False,
        "prompt_injection_detected": False,
        "prompt_injection_evidence": [],
    }


class _ScenarioProvider:
    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del schema
        scenario = SimulationScenario(str(context["simulation_scenario"]))
        attempt = cast(int, context["attempt"])
        if scenario is SimulationScenario.PROVIDER_SLOW:
            time.sleep(0.001)
        if scenario is SimulationScenario.PROVIDER_DOWN:
            raise ProviderError("provider_unavailable")
        if scenario is SimulationScenario.TOOL_FAILED:
            raise ProviderError("tool_failed")
        if scenario is SimulationScenario.RETRY and attempt == 1:
            raise ProviderError("provider_timeout")
        return _valid_output(prompt_version)

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


def test_baseline_and_slow_provider_complete_synthetic_cases() -> None:
    provider = _ScenarioProvider()
    baseline = simulate_dataset(provider, scenario=SimulationScenario.BASELINE, cases=_CASES)
    slow = simulate_dataset(
        provider, scenario=SimulationScenario.PROVIDER_SLOW, cases=_CASES
    )

    assert baseline.dataset_version == DATASET_VERSION
    assert baseline.completed == len(_CASES)
    assert baseline.attempts == len(_CASES)
    assert slow.completed == len(_CASES)
    assert slow.latency_ms >= 0
    assert all(case.status is SimulationStatus.COMPLETED for case in slow.cases)


def test_provider_and_tool_failures_are_recorded_without_retry() -> None:
    provider = _ScenarioProvider()
    down = simulate_dataset(
        provider, scenario=SimulationScenario.PROVIDER_DOWN, cases=_CASES
    )
    tool = simulate_dataset(
        provider, scenario=SimulationScenario.TOOL_FAILED, cases=_CASES
    )

    assert down.failed == len(_CASES)
    assert down.attempts == len(_CASES)
    assert all(case.error_code == "provider_unavailable" for case in down.cases)
    assert tool.failed == len(_CASES)
    assert all(case.error_code == "tool_failed" for case in tool.cases)


def test_approval_rejection_stops_before_provider_call() -> None:
    report = simulate_dataset(
        _ScenarioProvider(),
        scenario=SimulationScenario.APPROVAL_REJECTED,
        cases=_CASES,
    )

    assert report.stopped == len(_CASES)
    assert report.attempts == 0
    assert all(case.error_code == "approval_rejected" for case in report.cases)


def test_retry_succeeds_on_second_attempt() -> None:
    report = simulate_dataset(
        _ScenarioProvider(), scenario=SimulationScenario.RETRY, cases=_CASES
    )

    assert report.completed == len(_CASES)
    assert report.attempts == len(_CASES) * 2
    assert all(case.attempts == 2 for case in report.cases)


def test_simulation_report_has_no_candidate_pii() -> None:
    report = simulate_dataset(
        _ScenarioProvider(), scenario=SimulationScenario.BASELINE, cases=_CASES
    )

    serialized = json.dumps(report.model_dump())
    assert "Synthetic" not in serialized
    assert "@example.test" not in serialized
    assert str(uuid.uuid5(uuid.NAMESPACE_URL, "unrelated")) not in serialized


def test_invalid_max_attempts_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid_max_attempts"):
        simulate_dataset(
            _ScenarioProvider(),
            scenario=SimulationScenario.BASELINE,
            cases=_CASES,
            max_attempts=0,
        )
