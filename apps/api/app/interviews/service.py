from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import cast

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from app.agents.interview_assistant import (
    PROMPT_VERSION,
    build_context,
    get_candidate_profile,
    get_job_requirements,
)
from app.applications.models import Application
from app.assessment import context as assessment_context
from app.assessment.models import RequirementEvaluationStatus
from app.assessment.repositories import list_assessment_evaluations, list_assessments
from app.audit.service import record_audit
from app.candidates.models import Candidate
from app.core.logging import log_structured
from app.identity.models import MembershipRole
from app.identity.repositories import user_belongs_to_organization
from app.interviews.models import (
    InterviewDomainError,
    InterviewGuide,
    InterviewGuideStatus,
    InterviewQuestion,
    InterviewQuestionStatus,
)
from app.interviews.policies import (
    PolicyDecision,
    QuestionPolicyResult,
    evaluate_question,
)
from app.interviews.repositories import (
    get_guide_for_generation,
    get_revision,
    list_questions,
    next_version,
    save_revision,
)
from app.interviews.schemas import (
    InterviewQuestionCreate,
    InterviewQuestionDraft,
    InterviewQuestionsOutput,
)
from app.jobs.models import Job, JobVersion
from app.llm.provider import LLMProvider, ProviderError
from app.llm.registry import get_llm_provider

DETERMINISTIC_MODEL_VERSION = "deterministic-no-interview-questions-v1"
_RESOURCE_TYPE = "interview_guide"
_MAX_GAPS = 20
_MAX_STORED_QUESTIONS = 40
_GENERATION_ROLES = frozenset(
    {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.RECRUITER}
)
_GAP_STATUSES = frozenset(
    {RequirementEvaluationStatus.NOT_FOUND, RequirementEvaluationStatus.PARTIAL}
)


class InterviewGenerationError(InterviewDomainError):
    """Error determinista con código estable; sin PII ni texto del modelo."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _log_event(
    level: int,
    event: str,
    *,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    guide_id: uuid.UUID,
    result: str,
    correlation_id: str,
    detail: str = "",
) -> None:
    """Logs con IDs y conteos: nunca preguntas, citas, CV ni chain-of-thought."""
    message = (
        f"{event} application_id={application_id} guide_id={guide_id} "
        f"prompt_version={PROMPT_VERSION} result={result} correlation_id={correlation_id}"
    )
    if detail:
        message += f" detail={detail}"
    log_structured(
        level, message, correlation_id=correlation_id, organization_id=str(organization_id)
    )


def _resolve(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> tuple[Application, Job, Candidate, JobVersion]:
    """Resuelve recursos del tenant; la versión de vacante es inmutable."""
    resolved = assessment_context.resolve_application(db, organization_id, application_id)
    if resolved is None:
        raise InterviewGenerationError("not_found")
    return resolved


def _gaps_from_assessments(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    job_version_id: uuid.UUID,
) -> list[dict[str, object]]:
    """Brechas `not_found`/`partial` de la evaluación vigente de esa versión."""
    assessments = list_assessments(db, organization_id, application_id=application_id)
    matching = [item for item in assessments if item.job_version_id == job_version_id]
    if not matching:
        return []
    latest = max(matching, key=lambda item: (item.created_at, item.id))
    gaps: list[dict[str, object]] = []
    for evaluation in list_assessment_evaluations(db, organization_id, latest.id):
        if evaluation.status in _GAP_STATUSES:
            gaps.append(
                {
                    "requirement_id": str(evaluation.requirement_id),
                    "status": evaluation.status.value,
                }
            )
        if len(gaps) >= _MAX_GAPS:
            break
    return gaps


def _deterministic_output(reason: str) -> InterviewQuestionsOutput:
    """Sin requisitos o brechas: guía vacía y revisión humana, sin proveedor."""
    return InterviewQuestionsOutput(
        questions=[],
        model_version=DETERMINISTIC_MODEL_VERSION,
        prompt_version=PROMPT_VERSION,
        limitations=[reason],
        review_required=True,
    )


def _generate_output(
    provider: LLMProvider, context: dict[str, object]
) -> InterviewQuestionsOutput:
    """Invoca al proveedor y valida el contrato antes de cualquier persistencia."""
    try:
        raw = provider.generate_structured_output(
            PROMPT_VERSION, InterviewQuestionsOutput, context
        )
    except ProviderError as exc:
        raise InterviewGenerationError(exc.code) from None
    except (TypeError, ValueError):
        raise InterviewGenerationError("invalid_provider_output") from None
    try:
        output = InterviewQuestionsOutput.model_validate(raw)
    except (ValidationError, TypeError):
        raise InterviewGenerationError("invalid_provider_output") from None
    if output.prompt_version != PROMPT_VERSION:
        raise InterviewGenerationError("prompt_version_mismatch")
    return output


def _apply_policies(
    output: InterviewQuestionsOutput, allowed_requirement_ids: set[uuid.UUID]
) -> tuple[
    list[tuple[InterviewQuestionDraft, int]],
    list[tuple[InterviewQuestionDraft, QuestionPolicyResult, int]],
]:
    """El código decide qué preguntas entran; el modelo nunca decide políticas."""
    accepted: list[tuple[InterviewQuestionDraft, int]] = []
    rejected: list[tuple[InterviewQuestionDraft, QuestionPolicyResult, int]] = []
    position = 1
    for draft in output.questions:
        decision = evaluate_question(draft, allowed_requirement_ids)
        if decision.decision is PolicyDecision.ACCEPTED:
            accepted.append((draft, position))
        else:
            rejected.append((draft, decision, position))
        position += 1
    return accepted, rejected


def _question_snapshot(draft: InterviewQuestionDraft, position: int) -> dict[str, object]:
    return {
        "position": position,
        "requirement_id": str(draft.requirement_id),
        "category": draft.category.value,
        "question": draft.question,
        "evidence_focus": draft.evidence_focus,
        "competency": draft.competency,
        "limitations": list(draft.limitations),
        "review_required": bool(draft.limitations),
    }


def _add_question(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    guide_id: uuid.UUID,
    actor_id: uuid.UUID,
    draft: InterviewQuestionDraft,
    position: int,
    status: InterviewQuestionStatus,
    review_required: bool,
    model_version: str,
) -> None:
    payload = InterviewQuestionCreate.model_validate(
        {
            "requirement_id": draft.requirement_id,
            "position": position,
            "category": draft.category,
            "question": draft.question,
            "evidence_focus": draft.evidence_focus,
            "competency": draft.competency,
            "review_required": review_required,
            "model_version": model_version,
            "prompt_version": PROMPT_VERSION,
        }
    )
    db.add(
        InterviewQuestion(
            organization_id=organization_id,
            guide_id=guide_id,
            created_by=actor_id,
            requirement_id=payload.requirement_id,
            position=payload.position,
            category=payload.category,
            question=payload.question,
            evidence_focus=payload.evidence_focus,
            competency=payload.competency,
            status=status,
            review_required=payload.review_required,
            model_version=payload.model_version,
            prompt_version=payload.prompt_version,
        )
    )


def _rejection_reasons(snapshot: Mapping[str, object]) -> dict[int, str]:
    reasons: dict[int, str] = {}
    raw = snapshot.get("rejected_questions", [])
    if not isinstance(raw, (list, tuple)):
        return reasons
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        position = item.get("position")
        reason = item.get("reason_code")
        if isinstance(position, int) and isinstance(reason, str):
            reasons[position] = reason
    return reasons


def _serialize_question(question: InterviewQuestion, reason: str | None) -> dict[str, object]:
    result: dict[str, object] = {
        "id": question.id,
        "requirement_id": question.requirement_id,
        "category": question.category.value,
        "question": question.question,
        "evidence_focus": question.evidence_focus,
        "competency": question.competency,
        "position": question.position,
        "status": question.status.value,
        "review_required": question.review_required,
    }
    if reason is not None:
        result["reason_code"] = reason
    return result


def _result(
    db: DBSession,
    organization_id: uuid.UUID,
    guide: InterviewGuide,
    *,
    created: bool,
) -> dict[str, object]:
    revision = get_revision(db, organization_id, guide.id, guide.version)
    snapshot: Mapping[str, object] = revision.snapshot if revision is not None else {}
    reasons = _rejection_reasons(snapshot)
    stored = list_questions(
        db, organization_id, guide_id=guide.id, limit=_MAX_STORED_QUESTIONS
    )
    questions = [
        _serialize_question(item, None)
        for item in stored
        if item.status is not InterviewQuestionStatus.REJECTED
    ]
    rejected = [
        _serialize_question(item, reasons.get(item.position, "policy_rejected"))
        for item in stored
        if item.status is InterviewQuestionStatus.REJECTED
    ]
    raw_job_version = snapshot.get("job_version_id")
    job_version_id: uuid.UUID | None = None
    if isinstance(raw_job_version, str):
        try:
            job_version_id = uuid.UUID(raw_job_version)
        except ValueError:
            job_version_id = None
    limitations = snapshot.get("limitations", [])
    return {
        "guide_id": guide.id,
        "application_id": guide.application_id,
        "version": guide.version,
        "status": guide.status.value,
        "job_version_id": job_version_id,
        "prompt_version": snapshot.get("prompt_version", PROMPT_VERSION),
        "model_version": snapshot.get("model_version", DETERMINISTIC_MODEL_VERSION),
        "questions": questions,
        "rejected_questions": rejected,
        "limitations": list(limitations) if isinstance(limitations, (list, tuple)) else [],
        "review_required": bool(snapshot.get("review_required", True)),
        "needs_review": bool(snapshot.get("needs_review", True)),
        "created": created,
    }


def generate_guide(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    application_id: uuid.UUID,
    provider: LLMProvider | None = None,
) -> dict[str, object]:
    """Genera una guía en `draft`, sin publicar ni decidir contratación.

    Autoriza por rol y tenant antes de leer recursos; idempotente por
    `(application_id, job_version_id, prompt_version)`. Las preguntas se validan
    con esquema estricto y políticas deterministas; las rechazadas quedan fuera
    de la lista publicable y fuerzan revisión humana.
    """
    correlation_id = str(uuid.uuid4())
    if actor_role not in _GENERATION_ROLES:
        raise InterviewGenerationError("forbidden")
    if not user_belongs_to_organization(db, actor_id, organization_id):
        raise InterviewGenerationError("forbidden")

    _, _, _, version = _resolve(db, organization_id, application_id)
    existing = get_guide_for_generation(
        db,
        organization_id,
        application_id,
        job_version_id=version.id,
        prompt_version=PROMPT_VERSION,
    )
    if existing is not None:
        return _result(db, organization_id, existing, created=False)

    gaps = _gaps_from_assessments(db, organization_id, application_id, version.id)
    requirements_result = get_job_requirements(db, organization_id, application_id)
    requirements = cast(list[dict[str, object]], requirements_result["requirements"])
    profile = get_candidate_profile(db, organization_id, application_id)
    context = build_context(
        organization_id=organization_id,
        application_id=application_id,
        requirements=requirements_result,
        profile=profile,
        gaps=gaps,
    )

    if not requirements or not gaps:
        output = _deterministic_output(
            "requirements_missing" if not requirements else "no_assessment_gaps"
        )
    else:
        output = _generate_output(provider or get_llm_provider(), context)

    allowed = {uuid.UUID(str(item["requirement_id"])) for item in requirements}
    accepted, rejected = _apply_policies(output, allowed)
    needs_review = bool(
        output.review_required or output.limitations or rejected or not accepted
    )

    reject_codes: list[str] = []
    for _, decision, _ in rejected:
        if decision.reason_code is not None:
            reject_codes.append(decision.reason_code)
    limitations = [*output.limitations, *reject_codes]
    snapshot: dict[str, object] = {
        "application_id": str(application_id),
        "job_version_id": str(version.id),
        "prompt_version": PROMPT_VERSION,
        "model_version": output.model_version,
        "review_required": needs_review,
        "needs_review": needs_review,
        "limitations": limitations[:20],
        "questions": [_question_snapshot(draft, pos) for draft, pos in accepted],
        "rejected_questions": [
            {
                "position": pos,
                "requirement_id": str(draft.requirement_id),
                "category": draft.category.value,
                "reason_code": decision.reason_code or "policy_rejected",
            }
            for draft, decision, pos in rejected
        ],
    }

    try:
        guide_version = next_version(db, organization_id, application_id)
        guide = InterviewGuide(
            organization_id=organization_id,
            application_id=application_id,
            status=InterviewGuideStatus.DRAFT,
            version=guide_version,
            title=f"Guía de entrevista v{guide_version}",
            created_by=actor_id,
        )
        db.add(guide)
        db.flush()
        for draft, pos in accepted:
            _add_question(
                db,
                organization_id=organization_id,
                guide_id=guide.id,
                actor_id=actor_id,
                draft=draft,
                position=pos,
                status=InterviewQuestionStatus.DRAFT,
                review_required=needs_review or bool(draft.limitations),
                model_version=output.model_version,
            )
        for draft, _decision, pos in rejected:
            _add_question(
                db,
                organization_id=organization_id,
                guide_id=guide.id,
                actor_id=actor_id,
                draft=draft,
                position=pos,
                status=InterviewQuestionStatus.REJECTED,
                review_required=True,
                model_version=output.model_version,
            )
        save_revision(
            db,
            organization_id=organization_id,
            guide_id=guide.id,
            version=guide.version,
            snapshot=snapshot,
            created_by=actor_id,
        )
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="interview.guide_generated",
            resource_type=_RESOURCE_TYPE,
            resource_id=guide.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_guide_for_generation(
            db,
            organization_id,
            application_id,
            job_version_id=version.id,
            prompt_version=PROMPT_VERSION,
        )
        if existing is not None:
            return _result(db, organization_id, existing, created=False)
        raise InterviewGenerationError("guide_conflict") from None
    except SQLAlchemyError:
        db.rollback()
        raise

    _log_event(
        logging.INFO,
        "interview.guide_generated",
        organization_id=organization_id,
        application_id=application_id,
        guide_id=guide.id,
        result=InterviewGuideStatus.DRAFT.value,
        correlation_id=correlation_id,
        detail=f"accepted={len(accepted)} rejected={len(rejected)}",
    )
    if needs_review:
        _log_event(
            logging.INFO,
            "interview.guide_review_required",
            organization_id=organization_id,
            application_id=application_id,
            guide_id=guide.id,
            result="needs_review",
            correlation_id=correlation_id,
            detail=f"rejected={len(rejected)}",
        )
    return _result(db, organization_id, guide, created=True)
