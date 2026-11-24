from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.agents.matching_analyst import PROMPT_VERSION
from app.applications.models import Application
from app.applications.repositories import get_application as get_application_record
from app.assessment import context as assessment_context
from app.assessment.matching_schema import AssessmentOutput, MatchingEvidenceRef, MatchingResult
from app.assessment.models import (
    Assessment,
    AssessmentStatus,
    RequirementEvaluation,
    RequirementEvaluationStatus,
)
from app.assessment.repositories import (
    count_assessments,
    create_assessment,
    get_assessment,
    get_assessment_evaluation,
    list_assessment_evaluations,
    list_assessments,
    save_evaluation,
    update_evaluation_review,
    update_summary,
)
from app.assessment.schemas import (
    AssessmentComparisonResult,
    AssessmentListResponse,
    AssessmentResult,
    ComparisonVersion,
    EvidenceRef,
    EvidenceRefsChange,
    ExplanationChange,
    RequirementComparison,
    RequirementEvaluationResult,
    ReviewDecision,
    ReviewRequiredChange,
    StatusChange,
    assessment_result,
)
from app.audit.service import record_audit
from app.candidates.models import Candidate
from app.candidates.repositories import get_candidate as get_candidate_record
from app.core.logging import log_structured
from app.identity.models import MembershipRole
from app.identity.repositories import user_belongs_to_organization
from app.jobs.models import Job, JobVersion
from app.llm.provider import ProviderError
from app.llm.registry import get_llm_provider

DETERMINISTIC_MODEL_VERSION = "deterministic-no-confirmed-fields-v1"
_RESOURCE_TYPE = "assessment"
_REVIEW_ROLES = frozenset(
    {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.RECRUITER}
)
_RESOLVED_EVALUATIONS = frozenset(
    {RequirementEvaluationStatus.SUPPORTED, RequirementEvaluationStatus.NOT_FOUND}
)
_EvidenceKey = tuple[str, str, int, str]


class AssessmentDomainError(Exception):
    """Error determinista del dominio; mensaje es solo un código estable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _NormalizedEvaluation:
    requirement_id: uuid.UUID
    status: RequirementEvaluationStatus
    evidence: list[dict[str, object]]
    explanation: str
    limitations: list[str]
    review_required: bool


@dataclass(frozen=True)
class AssessmentRunOutcome:
    """Resultado visible para HTTP: permite 201/200 sin duplicar evaluaciones."""

    result: AssessmentResult
    created: bool


def _log_event(
    level: int,
    event: str,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    job_version_id: uuid.UUID,
    result: str,
    correlation_id: str,
    error_code: str | None = None,
    detail: str = "",
) -> None:
    """Logs con IDs y códigos: nunca CV, citas, valores de campo ni explicaciones."""
    message = (
        f"{event} application_id={application_id} job_version_id={job_version_id} "
        f"prompt_version={PROMPT_VERSION} result={result} correlation_id={correlation_id}"
    )
    if error_code:
        message += f" error_code={error_code}"
    if detail:
        message += f" detail={detail}"
    log_structured(
        level, message, correlation_id=correlation_id, organization_id=str(organization_id)
    )


def _find_existing(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    job_version_id: uuid.UUID,
) -> Assessment | None:
    stmt = select(Assessment).where(
        Assessment.organization_id == organization_id,
        Assessment.application_id == application_id,
        Assessment.job_version_id == job_version_id,
        Assessment.prompt_version == PROMPT_VERSION,
    )
    return db.execute(stmt).scalar_one_or_none()


def _resolve_for_write(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> tuple[Application, Job, Candidate, JobVersion]:
    """Autoriza al miembro del tenant y resuelve la versión inmutable de la vacante."""
    if not user_belongs_to_organization(db, actor_id, organization_id):
        raise AssessmentDomainError("forbidden")
    resolved = assessment_context.resolve_application(db, organization_id, application_id)
    if resolved is None:
        raise AssessmentDomainError("not_found")
    return resolved


def _allowed_evidence(
    context: dict[str, object],
) -> dict[_EvidenceKey, set[int | None]]:
    untrusted = cast(dict[str, object], context["untrusted_candidate_data"])
    raw = cast(list[dict[str, object]], untrusted["evidence"])
    allowed: dict[_EvidenceKey, set[int | None]] = {}
    for item in raw:
        page = item["page"]
        if not isinstance(page, int):
            continue
        key = (
            str(item["document_id"]),
            str(item["field_name"]),
            page,
            str(item["quote"]),
        )
        offset = item["offset"]
        allowed.setdefault(key, set()).add(
            int(offset) if isinstance(offset, int) else None
        )
    return allowed


def _ref_is_allowed(
    ref: MatchingEvidenceRef, allowed: dict[_EvidenceKey, set[int | None]]
) -> bool:
    key = (str(ref.document_id), ref.field_name, ref.page, ref.quote)
    offsets = allowed.get(key)
    if offsets is None:
        return False
    return ref.offset is None or ref.offset in offsets


def _ref_to_json(ref: MatchingEvidenceRef) -> dict[str, object]:
    data: dict[str, object] = {
        "document_id": str(ref.document_id),
        "field_name": ref.field_name,
        "page": ref.page,
        "quote": ref.quote,
    }
    if ref.offset is not None:
        data["offset"] = ref.offset
    return data


def _deterministic_output(requirements: list[dict[str, object]]) -> AssessmentOutput:
    """Sin campos confirmados: resultado explícito, determinista y sin proveedor."""
    evaluations: list[MatchingResult] = []
    gaps: list[str] = []
    questions: list[str] = []
    for item in requirements:
        evaluations.append(
            MatchingResult(
                requirement_id=uuid.UUID(str(item["requirement_id"])),
                status=RequirementEvaluationStatus.NOT_FOUND,
                evidence_refs=[],
                explanation="Sin campos confirmados para este requisito",
                limitations=["no_confirmed_fields"],
                review_required=True,
            )
        )
        gaps.append(str(item["description"])[:200])
        questions.append("Solicitar evidencia profesional confirmada para este requisito")
    return AssessmentOutput(
        evaluations=evaluations,
        strengths=[],
        gaps=gaps,
        questions=questions,
        limitations=["no_confirmed_fields"],
        review_required=True,
        model_version=DETERMINISTIC_MODEL_VERSION,
        prompt_version=PROMPT_VERSION,
    )


def _normalize(
    output: AssessmentOutput, context: dict[str, object]
) -> list[_NormalizedEvaluation]:
    """Verifica cada cita y-classifica estados; el LLM no decide por sí solo."""
    requirements = cast(list[dict[str, object]], context["requirements"])
    untrusted = cast(dict[str, object], context["untrusted_candidate_data"])
    contradictions = cast(list[str], untrusted["contradictions"])
    allowed = _allowed_evidence(context)
    results: dict[uuid.UUID, MatchingResult] = {}
    for candidate_result in output.evaluations:
        results.setdefault(candidate_result.requirement_id, candidate_result)

    normalized: list[_NormalizedEvaluation] = []
    for item in requirements:
        requirement_id = uuid.UUID(str(item["requirement_id"]))
        result = results.get(requirement_id)
        if result is None:
            normalized.append(
                _NormalizedEvaluation(
                    requirement_id=requirement_id,
                    status=RequirementEvaluationStatus.NOT_FOUND,
                    evidence=[],
                    explanation="El proveedor no evaluó este requisito",
                    limitations=["missing_evaluation"],
                    review_required=True,
                )
            )
            continue

        invalid = False
        valid_refs: list[MatchingEvidenceRef] = []
        for ref in result.evidence_refs:
            if _ref_is_allowed(ref, allowed):
                valid_refs.append(ref)
            else:
                invalid = True
        status = result.status
        limitations = list(result.limitations)
        if contradictions:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            valid_refs = []
            limitations.append("conflicting_confirmed_fields")
        elif invalid:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            valid_refs = []
            limitations.append("invalid_evidence_dropped")
        elif status in (
            RequirementEvaluationStatus.SUPPORTED,
            RequirementEvaluationStatus.PARTIAL,
        ) and not valid_refs:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            limitations.append("missing_evidence")
        elif status is RequirementEvaluationStatus.NOT_FOUND and valid_refs:
            status = RequirementEvaluationStatus.NEEDS_REVIEW
            valid_refs = []
            limitations.append("inconsistent_no_evidence_result")

        review_required = result.review_required or status in (
            RequirementEvaluationStatus.NEEDS_REVIEW,
            RequirementEvaluationStatus.NOT_FOUND,
        )
        normalized.append(
            _NormalizedEvaluation(
                requirement_id=requirement_id,
                status=status,
                evidence=[_ref_to_json(ref) for ref in valid_refs],
                explanation=result.explanation,
                limitations=limitations,
                review_required=review_required,
            )
        )
    return normalized


def _persist(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    job_version_id: uuid.UUID,
    candidate_id: uuid.UUID,
    actor_id: uuid.UUID,
    output: AssessmentOutput,
    evaluations: list[_NormalizedEvaluation],
    status: AssessmentStatus,
    summary: dict[str, object],
    limitations: list[str],
) -> Assessment:
    try:
        assessment = create_assessment(
            db,
            organization_id=organization_id,
            application_id=application_id,
            job_version_id=job_version_id,
            candidate_id=candidate_id,
            created_by=actor_id,
            model_version=output.model_version,
            prompt_version=PROMPT_VERSION,
        )
        for evaluation in evaluations:
            save_evaluation(
                db,
                assessment_id=assessment.id,
                requirement_id=evaluation.requirement_id,
                status=evaluation.status,
                explanation=evaluation.explanation,
                evidence=evaluation.evidence,
                limitations=evaluation.limitations,
                review_required=evaluation.review_required,
            )
        update_summary(
            db, assessment, status=status, summary=summary, limitations=limitations
        )
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="assessment.created",
            resource_type=_RESOURCE_TYPE,
            resource_id=assessment.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_existing(db, organization_id, application_id, job_version_id)
        if existing is not None:
            return existing
        raise AssessmentDomainError("assessment_conflict") from None
    except SQLAlchemyError:
        db.rollback()
        raise
    return assessment


def run_assessment(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> Assessment:
    """Evalúa una postulación contra la última versión inmmutable de su vacante.

    Autorización por tenant y miembro, idempotencia por versión/prompt, evidencias
    verificadas ysin score, ranking ni decisión automática.
    """
    correlation_id = str(uuid.uuid4())
    resolved = _resolve_for_write(db, organization_id, application_id, actor_id)
    application, _, candidate, version = resolved

    existing = _find_existing(db, organization_id, application_id, version.id)
    if existing is not None:
        return existing

    context = assessment_context.build_context(db, organization_id, application_id)
    requirements = cast(list[dict[str, object]], context["requirements"])
    untrusted = cast(dict[str, object], context["untrusted_candidate_data"])
    confirmed_fields = cast(list[object], untrusted["confirmed_fields"])
    contradictions = cast(list[str], untrusted["contradictions"])

    if not confirmed_fields:
        output = _deterministic_output(requirements)
    else:
        try:
            raw = get_llm_provider().generate_structured_output(
                PROMPT_VERSION, AssessmentOutput, context
            )
        except ProviderError as exc:
            _log_event(
                logging.WARNING,
                "assessment.failed",
                organization_id=organization_id,
                application_id=application_id,
                job_version_id=version.id,
                result="failed",
                correlation_id=correlation_id,
                error_code=exc.code,
            )
            raise AssessmentDomainError(exc.code) from None
        except (TypeError, ValueError):
            _log_event(
                logging.WARNING,
                "assessment.failed",
                organization_id=organization_id,
                application_id=application_id,
                job_version_id=version.id,
                result="failed",
                correlation_id=correlation_id,
                error_code="invalid_provider_output",
            )
            raise AssessmentDomainError("invalid_provider_output") from None
        try:
            output = AssessmentOutput.model_validate(raw)
        except ValidationError:
            _log_event(
                logging.WARNING,
                "assessment.failed",
                organization_id=organization_id,
                application_id=application_id,
                job_version_id=version.id,
                result="failed",
                correlation_id=correlation_id,
                error_code="invalid_provider_output",
            )
            raise AssessmentDomainError("invalid_provider_output") from None
        if output.prompt_version != PROMPT_VERSION:
            _log_event(
                logging.WARNING,
                "assessment.failed",
                organization_id=organization_id,
                application_id=application_id,
                job_version_id=version.id,
                result="failed",
                correlation_id=correlation_id,
                error_code="prompt_version_mismatch",
            )
            raise AssessmentDomainError("prompt_version_mismatch")

    evaluations = _normalize(output, context)
    limitations = list(output.limitations)
    limitations.extend(cast(list[str], context["missing"]))
    if contradictions:
        limitations.append("conflicting_confirmed_fields")
    status = (
        AssessmentStatus.NEEDS_REVIEW
        if output.review_required or any(item.review_required for item in evaluations)
        else AssessmentStatus.COMPLETED
    )
    summary: dict[str, object] = {
        "strengths": list(output.strengths),
        "gaps": list(output.gaps),
        "questions": list(output.questions),
    }

    assessment = _persist(
        db,
        organization_id=organization_id,
        application_id=application_id,
        job_version_id=version.id,
        candidate_id=candidate.id,
        actor_id=actor_id,
        output=output,
        evaluations=evaluations,
        status=status,
        summary=summary,
        limitations=limitations,
    )
    needs_review = status is AssessmentStatus.NEEDS_REVIEW
    _log_event(
        logging.INFO,
        "assessment.created",
        organization_id=organization_id,
        application_id=application_id,
        job_version_id=version.id,
        result=status.value,
        correlation_id=correlation_id,
        detail=(
            f"requirements={len(evaluations)} "
            f"review_required={str(needs_review).lower()} "
            f"model_version={output.model_version}"
        ),
    )
    return assessment


def _detail(
    db: DBSession, organization_id: uuid.UUID, assessment: Assessment
) -> AssessmentResult:
    evaluations = list_assessment_evaluations(db, organization_id, assessment.id)
    return assessment_result(assessment, evaluations)


def run_assessment_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> AssessmentRunOutcome:
    """Ejecuta o reutiliza la evaluación de la versión vigente; expone si la creó."""
    resolved = _resolve_for_write(db, organization_id, application_id, actor_id)
    version = resolved[3]
    existing = _find_existing(db, organization_id, application_id, version.id)
    if existing is not None:
        return AssessmentRunOutcome(result=_detail(db, organization_id, existing), created=False)
    assessment = run_assessment(
        db,
        organization_id=organization_id,
        application_id=application_id,
        actor_id=actor_id,
    )
    return AssessmentRunOutcome(result=_detail(db, organization_id, assessment), created=True)


def list_assessments_for_application(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Assessment], int]:
    """Lista las evaluaciones de una postulación del tenant; filtro siempre por org."""
    if get_application_record(db, organization_id, application_id) is None:
        raise AssessmentDomainError("not_found")
    items = list_assessments(
        db,
        organization_id,
        application_id=application_id,
        limit=limit,
        offset=offset,
    )
    total = count_assessments(db, organization_id, application_id=application_id)
    return items, total


def list_assessments_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID | None,
    candidate_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> AssessmentListResponse:
    """Contrato paginado; los filtros de otro tenant se rechazan sin filtrar datos."""
    if application_id is not None and get_application_record(
        db, organization_id, application_id
    ) is None:
        raise AssessmentDomainError("not_found")
    if candidate_id is not None and get_candidate_record(
        db, organization_id, candidate_id
    ) is None:
        raise AssessmentDomainError("not_found")
    items = list_assessments(
        db,
        organization_id,
        application_id=application_id,
        candidate_id=candidate_id,
        limit=limit,
        offset=offset,
    )
    total = count_assessments(
        db, organization_id, application_id=application_id, candidate_id=candidate_id
    )
    return AssessmentListResponse(
        items=[assessment_result(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_assessment_detail(
    db: DBSession, *, organization_id: uuid.UUID, assessment_id: uuid.UUID
) -> AssessmentResult:
    """Detalle con criterios y evidencia verificada, sin datos privados del CV."""
    assessment = get_assessment(db, organization_id, assessment_id)
    if assessment is None:
        raise AssessmentDomainError("not_found")
    return _detail(db, organization_id, assessment)


def _require_reviewer(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
) -> None:
    if actor_role not in _REVIEW_ROLES or not user_belongs_to_organization(
        db, actor_id, organization_id
    ):
        raise AssessmentDomainError("forbidden")


def _commit_or_rollback(db: DBSession) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def review_evaluation(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    assessment_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    decision: ReviewDecision,
) -> RequirementEvaluationResult:
    """Registra quién y cuándo corrigió un criterio; sin valores del CV en auditoría."""
    _require_reviewer(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    assessment = get_assessment(db, organization_id, assessment_id)
    evaluation = get_assessment_evaluation(
        db, organization_id, assessment_id, evaluation_id
    )
    if assessment is None or evaluation is None:
        raise AssessmentDomainError("not_found")

    updated = update_evaluation_review(
        db,
        evaluation,
        status=decision.status,
        explanation=decision.explanation,
        reviewed_by=actor_id,
        reviewed_at=datetime.now(UTC),
        review_required=decision.status is RequirementEvaluationStatus.NEEDS_REVIEW,
    )
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="assessment.reviewed",
        resource_type=_RESOURCE_TYPE,
        resource_id=assessment.id,
    )
    _commit_or_rollback(db)
    return RequirementEvaluationResult.model_validate(updated)


def complete_review(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    assessment_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
) -> AssessmentResult:
    """Cierra la revisión solo si no quedan criterios sin revisar y pendientes."""
    _require_reviewer(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    assessment = get_assessment(db, organization_id, assessment_id)
    if assessment is None:
        raise AssessmentDomainError("not_found")
    evaluations = list_assessment_evaluations(db, organization_id, assessment_id)
    pending = [
        item
        for item in evaluations
        if item.reviewed_by is None and item.status not in _RESOLVED_EVALUATIONS
    ]
    if pending:
        raise AssessmentDomainError("review_pending")

    update_summary(
        db,
        assessment,
        status=AssessmentStatus.COMPLETED,
        summary=assessment.summary,
        limitations=assessment.limitations,
    )
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="assessment.review_completed",
        resource_type=_RESOURCE_TYPE,
        resource_id=assessment.id,
    )
    _commit_or_rollback(db)
    return assessment_result(assessment, evaluations)


def _evidence_refs(item: RequirementEvaluation | None) -> list[EvidenceRef]:
    if item is None:
        return []
    return [EvidenceRef.model_validate(ref) for ref in item.evidence]


def _version(assessment: Assessment) -> ComparisonVersion:
    return ComparisonVersion(
        assessment_id=assessment.id,
        status=assessment.status,
        model_version=assessment.model_version,
        prompt_version=assessment.prompt_version,
    )


def _by_requirement(
    items: Sequence[RequirementEvaluation],
) -> dict[uuid.UUID, RequirementEvaluation]:
    return {item.requirement_id: item for item in items}


def compare_assessments(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    base_id: uuid.UUID,
    other_id: uuid.UUID,
) -> AssessmentComparisonResult:
    """Compara dos versiones de la misma postulación del tenant, sin score."""
    base = get_assessment(db, organization_id, base_id)
    other = get_assessment(db, organization_id, other_id)
    if base is None or other is None:
        raise AssessmentDomainError("not_found")
    if base.application_id != other.application_id:
        raise AssessmentDomainError("application_mismatch")

    base_items = _by_requirement(
        list_assessment_evaluations(db, organization_id, base.id)
    )
    other_items = _by_requirement(
        list_assessment_evaluations(db, organization_id, other.id)
    )
    changes: list[RequirementComparison] = []
    for requirement_id in sorted(set(base_items) | set(other_items), key=str):
        before = base_items.get(requirement_id)
        after = other_items.get(requirement_id)
        before_status = before.status if before is not None else None
        after_status = after.status if after is not None else None
        before_explanation = before.explanation if before is not None else None
        after_explanation = after.explanation if after is not None else None
        before_evidence = _evidence_refs(before)
        after_evidence = _evidence_refs(after)
        before_review = before.review_required if before is not None else None
        after_review = after.review_required if after is not None else None
        changes.append(
            RequirementComparison(
                requirement_id=requirement_id,
                status=StatusChange(
                    before=before_status,
                    after=after_status,
                    changed=before_status != after_status,
                ),
                explanation=ExplanationChange(
                    before=before_explanation,
                    after=after_explanation,
                    changed=before_explanation != after_explanation,
                ),
                evidence_refs=EvidenceRefsChange(
                    before=before_evidence,
                    after=after_evidence,
                    changed=before_evidence != after_evidence,
                ),
                review_required=ReviewRequiredChange(
                    before=before_review,
                    after=after_review,
                    changed=before_review != after_review,
                ),
            )
        )
    return AssessmentComparisonResult(
        base=_version(base),
        target=_version(other),
        changes=changes,
    )
