from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.cv_analyst import PROMPT_VERSION, AnalysisContext, PageContext
from app.agents.extraction_schema import ExtractedProfile
from app.evaluation.dataset import DATASET_CASES, DATASET_VERSION, DatasetCase
from app.llm.provider import LLMProvider, ProviderError

_EVALUATION_ORGANIZATION = uuid.uuid5(uuid.NAMESPACE_URL, "talentos-evaluation-organization")


class SimulationScenario(StrEnum):
    BASELINE = "baseline"
    PROVIDER_SLOW = "provider_slow"
    PROVIDER_DOWN = "provider_down"
    TOOL_FAILED = "tool_failed"
    APPROVAL_REJECTED = "approval_rejected"
    RETRY = "retry"


class SimulationStatus(StrEnum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class SimulationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    scenario: SimulationScenario
    status: SimulationStatus
    attempts: int = Field(ge=0)
    error_code: str | None = None
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class SimulationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str
    prompt_version: str
    provider: str
    scenario: SimulationScenario
    cases: tuple[SimulationCaseResult, ...]
    completed: int
    stopped: int
    failed: int
    attempts: int
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


def _result(
    case: DatasetCase,
    scenario: SimulationScenario,
    status: SimulationStatus,
    *,
    attempts: int,
    latency_ms: float,
    error_code: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> SimulationCaseResult:
    return SimulationCaseResult(
        case_id=case.id,
        scenario=scenario,
        status=status,
        attempts=attempts,
        error_code=error_code,
        latency_ms=round(max(0.0, latency_ms), 3),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def simulate_case(
    provider: LLMProvider,
    case: DatasetCase,
    scenario: SimulationScenario,
    *,
    prompt_version: str = PROMPT_VERSION,
    max_attempts: int = 2,
) -> SimulationCaseResult:
    if max_attempts < 1:
        raise ValueError("invalid_max_attempts")
    if scenario is SimulationScenario.APPROVAL_REJECTED:
        return _result(
            case,
            scenario,
            SimulationStatus.STOPPED,
            attempts=0,
            latency_ms=0.0,
            error_code="approval_rejected",
        )

    document_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_VERSION}:simulation:{case.id}")
    base_context = AnalysisContext(
        document_id=document_id,
        organization_id=_EVALUATION_ORGANIZATION,
        pages=[PageContext(page=1, text=case.text)],
        prompt_version=prompt_version,
    ).as_provider_mapping()

    started = time.perf_counter()
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        context = dict(base_context)
        context["simulation_scenario"] = scenario.value
        context["attempt"] = attempt
        try:
            raw = provider.generate_structured_output(
                prompt_version, ExtractedProfile, context
            )
        except ProviderError as exc:
            if scenario is SimulationScenario.RETRY and attempt < max_attempts:
                continue
            return _result(
                case,
                scenario,
                SimulationStatus.FAILED,
                attempts=attempts,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=exc.code,
            )
        except (TypeError, ValueError):
            return _result(
                case,
                scenario,
                SimulationStatus.FAILED,
                attempts=attempts,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="invalid_provider_output",
            )
        try:
            profile = ExtractedProfile.model_validate(raw)
        except (ValidationError, TypeError, ValueError):
            return _result(
                case,
                scenario,
                SimulationStatus.FAILED,
                attempts=attempts,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="invalid_provider_output",
            )
        if profile.prompt_version != prompt_version:
            return _result(
                case,
                scenario,
                SimulationStatus.FAILED,
                attempts=attempts,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="prompt_version_mismatch",
            )

        usage: dict[str, int] = {}
        try:
            usage = provider.estimate_usage(prompt_version, context)
        except (ProviderError, TypeError, ValueError):
            pass
        return _result(
            case,
            scenario,
            SimulationStatus.COMPLETED,
            attempts=attempts,
            latency_ms=(time.perf_counter() - started) * 1000,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    return _result(
        case,
        scenario,
        SimulationStatus.FAILED,
        attempts=attempts,
        latency_ms=(time.perf_counter() - started) * 1000,
        error_code="max_attempts_exceeded",
    )


def simulate_dataset(
    provider: LLMProvider,
    *,
    scenario: SimulationScenario,
    cases: Sequence[DatasetCase] = DATASET_CASES,
    prompt_version: str = PROMPT_VERSION,
    max_attempts: int = 2,
    provider_label: str | None = None,
) -> SimulationReport:
    results = tuple(
        simulate_case(
            provider,
            case,
            scenario,
            prompt_version=prompt_version,
            max_attempts=max_attempts,
        )
        for case in cases
    )
    return SimulationReport(
        dataset_version=DATASET_VERSION,
        prompt_version=prompt_version,
        provider=provider_label or type(provider).__name__,
        scenario=scenario,
        cases=results,
        completed=sum(case.status is SimulationStatus.COMPLETED for case in results),
        stopped=sum(case.status is SimulationStatus.STOPPED for case in results),
        failed=sum(case.status is SimulationStatus.FAILED for case in results),
        attempts=sum(case.attempts for case in results),
        latency_ms=round(sum(case.latency_ms for case in results), 3),
        prompt_tokens=sum(case.prompt_tokens for case in results),
        completion_tokens=sum(case.completion_tokens for case in results),
    )
