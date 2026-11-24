from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
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
from app.agents.schemas import validate_safe_payload
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
    InterviewFeedback,
    InterviewFeedbackStatus,
    InterviewGuide,
    InterviewGuideRevision,
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
    allowed_requirement_ids,
    count_feedback,
    count_guides,
    count_revisions,
    get_guide,
    get_guide_for_generation,
    get_question,
    get_revision,
    list_feedback,
    list_guides,
    list_questions,
    list_revisions,
    next_version,
    save_revision,
)
from app.interviews.schemas import (
    GuideRevisionListResponse,
    GuideRevisionResult,
    InterviewFeedbackListResponse,
    InterviewFeedbackResult,
    InterviewFeedbackSubmitRequest,
    InterviewGuideDetail,
    InterviewGuideListResponse,
    InterviewGuideSummary,
    InterviewGuideUpdate,
    InterviewQuestionCreate,
    InterviewQuestionCreateRequest,
    InterviewQuestionDraft,
    InterviewQuestionResult,
    InterviewQuestionsOutput,
    InterviewQuestionUpdateRequest,
)
from app.jobs.models import Job, JobVersion
from app.llm.provider import LLMProvider, ProviderError
from app.llm.registry import get_llm_provider

DETERMINISTIC_MODEL_VERSION = "deterministic-no-interview-questions-v1"
MANUAL_MODEL_VERSION = "manual-review-v1"
MANUAL_PROMPT_VERSION = "manual-v1"
_RESOURCE_TYPE = "interview_guide"
_QUESTION_RESOURCE_TYPE = "interview_question"
_FEEDBACK_RESOURCE_TYPE = "interview_feedback"
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


class InterviewPolicyError(InterviewDomainError):
    """Pregunta rechazada por política; expone solo el código de la regla."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("policy_rejected")


def _log_api_event(
    event: str,
    *,
    organization_id: uuid.UUID,
    resource_id: uuid.UUID,
    result: str,
    correlation_id: str,
) -> None:
    """Logs de escritura con IDs y correlación; nunca texto de pregunta ni notas."""
    message = (
        f"{event} resource_id={resource_id} result={result} correlation_id={correlation_id}"
    )
    log_structured(
        logging.INFO,
        message,
        correlation_id=correlation_id,
        organization_id=str(organization_id),
    )


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
        "model_version": question.model_version,
        "prompt_version": question.prompt_version,
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


# --- API de guías, preguntas y feedback (reglas de negocio en el servicio). ---


def _authorize_write(
    db: DBSession,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
) -> None:
    """Autoriza por rol y membresía también dentro del dominio, no solo en la ruta."""
    if actor_role not in _GENERATION_ROLES or not user_belongs_to_organization(
        db, actor_id, organization_id
    ):
        raise InterviewGenerationError("forbidden")


def _require_guide(
    db: DBSession, organization_id: uuid.UUID, guide_id: uuid.UUID
) -> InterviewGuide:
    guide = get_guide(db, organization_id, guide_id)
    if guide is None:
        raise InterviewGenerationError("not_found")
    return guide


def _require_question(
    db: DBSession, organization_id: uuid.UUID, question_id: uuid.UUID
) -> InterviewQuestion:
    question = get_question(db, organization_id, question_id)
    if question is None:
        raise InterviewGenerationError("not_found")
    return question


def _parse_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _snapshot_for(
    db: DBSession, organization_id: uuid.UUID, guide: InterviewGuide
) -> dict[str, object]:
    """Copia saneada del snapshot vigente; nunca devuelve el dict ORM mutado."""
    revision = get_revision(db, organization_id, guide.id, guide.version)
    if revision is None:
        return {
            "application_id": str(guide.application_id),
            "title": guide.title,
            "status": guide.status.value,
            "version": guide.version,
            "limitations": [],
            "review_required": False,
            "needs_review": False,
            "questions": [],
        }
    return validate_safe_payload(dict(revision.snapshot))


def _snapshot_question(question: InterviewQuestion) -> dict[str, object]:
    return {
        "id": str(question.id),
        "requirement_id": str(question.requirement_id),
        "category": question.category.value,
        "question": question.question,
        "evidence_focus": question.evidence_focus,
        "competency": question.competency,
        "position": question.position,
        "status": question.status.value,
        "review_required": question.review_required,
        "model_version": question.model_version,
        "prompt_version": question.prompt_version,
    }


def _question_result(question: InterviewQuestion) -> InterviewQuestionResult:
    return InterviewQuestionResult.model_validate(_serialize_question(question, None))


def _has_pending(questions: list[InterviewQuestion]) -> bool:
    return any(
        item.status is not InterviewQuestionStatus.ARCHIVED
        and (item.status is InterviewQuestionStatus.REJECTED or item.review_required)
        for item in questions
    )


def _guide_detail(
    db: DBSession, organization_id: uuid.UUID, guide: InterviewGuide
) -> InterviewGuideDetail:
    revision = get_revision(db, organization_id, guide.id, guide.version)
    snapshot: Mapping[str, object] = (
        validate_safe_payload(dict(revision.snapshot)) if revision is not None else {}
    )
    limitations = snapshot.get("limitations", [])
    stored = list_questions(
        db, organization_id, guide_id=guide.id, limit=_MAX_STORED_QUESTIONS
    )
    questions = [
        _question_result(item)
        for item in stored
        if item.status is not InterviewQuestionStatus.ARCHIVED
    ]
    return InterviewGuideDetail(
        id=guide.id,
        application_id=guide.application_id,
        title=guide.title,
        status=guide.status,
        version=guide.version,
        created_at=guide.created_at,
        updated_at=guide.updated_at,
        job_version_id=_parse_uuid(snapshot.get("job_version_id")),
        model_version=(
            str(snapshot["model_version"])
            if isinstance(snapshot.get("model_version"), str)
            else None
        ),
        prompt_version=(
            str(snapshot["prompt_version"])
            if isinstance(snapshot.get("prompt_version"), str)
            else None
        ),
        limitations=[str(item) for item in limitations] if isinstance(limitations, list) else [],
        review_required=bool(snapshot.get("review_required", _has_pending(stored))),
        needs_review=bool(snapshot.get("needs_review", _has_pending(stored))),
        questions=questions,
    )


def _record_guide_change(
    db: DBSession,
    organization_id: uuid.UUID,
    guide: InterviewGuide,
    *,
    actor_id: uuid.UUID,
    title: str | None = None,
    status: InterviewGuideStatus | None = None,
) -> InterviewGuideRevision:
    """Incrementa la versión y congela un snapshot saneado de la guía editada."""
    snapshot = _snapshot_for(db, organization_id, guide)
    if title is not None:
        guide.title = title
    if status is not None and status is not guide.status:
        guide.transition_to(status)
    version = next_version(db, organization_id, guide.application_id)
    guide.version = version
    stored = list_questions(db, organization_id, guide_id=guide.id, limit=_MAX_STORED_QUESTIONS)
    snapshot.update(
        {
            "application_id": str(guide.application_id),
            "title": guide.title,
            "status": guide.status.value,
            "version": version,
            "review_required": _has_pending(stored),
            "needs_review": _has_pending(stored),
            "questions": [
                _snapshot_question(item)
                for item in stored
                if item.status is not InterviewQuestionStatus.ARCHIVED
            ],
        }
    )
    return save_revision(
        db,
        organization_id=organization_id,
        guide_id=guide.id,
        version=version,
        snapshot=snapshot,
        created_by=actor_id,
    )


def _validate_question_policy(
    db: DBSession,
    organization_id: uuid.UUID,
    guide: InterviewGuide,
    draft: InterviewQuestionDraft,
) -> None:
    """Revalida reglas deterministas contra el snapshot inmutable de la guía."""
    snapshot = _snapshot_for(db, organization_id, guide)
    job_version_id = _parse_uuid(snapshot.get("job_version_id"))
    allowed = (
        allowed_requirement_ids(db, organization_id, job_version_id)
        if job_version_id is not None
        else frozenset()
    )
    decision = evaluate_question(draft, allowed)
    if decision.decision is PolicyDecision.REJECTED:
        raise InterviewPolicyError(decision.reason_code or "policy_rejected")


def _draft_from_question(
    question: InterviewQuestion,
    *,
    question_text: str | None = None,
    evidence_focus: str | None = None,
    competency: str | None = None,
) -> InterviewQuestionDraft:
    return InterviewQuestionDraft.model_validate(
        {
            "requirement_id": question.requirement_id,
            "category": question.category,
            "question": question_text if question_text is not None else question.question,
            "evidence_focus": (
                evidence_focus if evidence_focus is not None else question.evidence_focus
            ),
            "competency": competency if competency is not None else question.competency,
            "limitations": [],
        }
    )


def list_guides_for_api(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    application_id: uuid.UUID | None = None,
    status: InterviewGuideStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> InterviewGuideListResponse:
    """Listado paginado y tenant-scoped; sin CV ni organization_id."""
    rows = list_guides(
        db,
        organization_id,
        application_id=application_id,
        limit=limit,
        offset=offset,
        status=status,
    )
    return InterviewGuideListResponse(
        items=[
            InterviewGuideSummary(
                id=row.id,
                application_id=row.application_id,
                title=row.title,
                status=row.status,
                version=row.version,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=count_guides(db, organization_id, application_id=application_id, status=status),
        limit=limit,
        offset=offset,
    )


def get_guide_detail_for_api(
    db: DBSession, organization_id: uuid.UUID, guide_id: uuid.UUID
) -> InterviewGuideDetail:
    """Detalle con preguntas trazables, sin CV, tenant ni rutas de storage."""
    return _guide_detail(db, organization_id, _require_guide(db, organization_id, guide_id))


def list_revisions_for_api(
    db: DBSession,
    organization_id: uuid.UUID,
    guide_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> GuideRevisionListResponse:
    """Historial saneado por versión; el recurso ajeno se traduce a 404."""
    guide = _require_guide(db, organization_id, guide_id)
    rows = list_revisions(db, organization_id, guide.id, limit=limit, offset=offset)
    return GuideRevisionListResponse(
        items=[
            GuideRevisionResult(
                id=row.id,
                version=row.version,
                created_by=row.created_by,
                created_at=row.created_at,
                snapshot=validate_safe_payload(dict(row.snapshot)),
            )
            for row in rows
        ],
        total=count_revisions(db, organization_id, guide.id),
        limit=limit,
        offset=offset,
    )


def update_guide_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    guide_id: uuid.UUID,
    payload: InterviewGuideUpdate,
    correlation_id: str,
) -> InterviewGuideDetail:
    """Edita título/estado, bloquea publicación con revisiones pendientes y audita."""
    _authorize_write(db, organization_id, actor_id, actor_role)
    guide = _require_guide(db, organization_id, guide_id)
    stored = list_questions(db, organization_id, guide_id=guide.id, limit=_MAX_STORED_QUESTIONS)
    if (
        payload.status is InterviewGuideStatus.PUBLISHED
        and guide.status is not InterviewGuideStatus.PUBLISHED
        and _has_pending(stored)
    ):
        raise InterviewGenerationError("publish_blocked")

    try:
        _record_guide_change(
            db,
            organization_id,
            guide,
            actor_id=actor_id,
            title=payload.title,
            status=payload.status,
        )
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="interview.guide_updated",
            resource_type=_RESOURCE_TYPE,
            resource_id=guide.id,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    _log_api_event(
        "interview.guide_updated",
        organization_id=organization_id,
        resource_id=guide.id,
        result=guide.status.value,
        correlation_id=correlation_id,
    )
    return _guide_detail(db, organization_id, guide)


def add_question_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    guide_id: uuid.UUID,
    payload: InterviewQuestionCreateRequest,
    correlation_id: str,
) -> InterviewQuestionResult:
    """Alta manual: revalida políticas y deja revisión versionada."""
    _authorize_write(db, organization_id, actor_id, actor_role)
    guide = _require_guide(db, organization_id, guide_id)
    draft = InterviewQuestionDraft.model_validate(
        {
            "requirement_id": payload.requirement_id,
            "category": payload.category,
            "question": payload.question,
            "evidence_focus": payload.evidence_focus,
            "competency": payload.competency,
            "limitations": [],
        }
    )
    _validate_question_policy(db, organization_id, guide, draft)
    question = InterviewQuestion(
        organization_id=organization_id,
        guide_id=guide.id,
        created_by=actor_id,
        requirement_id=draft.requirement_id,
        position=payload.position,
        category=draft.category,
        question=draft.question,
        evidence_focus=draft.evidence_focus,
        competency=draft.competency,
        status=InterviewQuestionStatus.DRAFT,
        review_required=payload.review_required,
        model_version=MANUAL_MODEL_VERSION,
        prompt_version=MANUAL_PROMPT_VERSION,
    )
    try:
        db.add(question)
        db.flush()
        _record_guide_change(db, organization_id, guide, actor_id=actor_id)
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="interview.question_added",
            resource_type=_QUESTION_RESOURCE_TYPE,
            resource_id=question.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise InterviewGenerationError("position_conflict") from None
    except SQLAlchemyError:
        db.rollback()
        raise
    _log_api_event(
        "interview.question_added",
        organization_id=organization_id,
        resource_id=question.id,
        result=InterviewQuestionStatus.DRAFT.value,
        correlation_id=correlation_id,
    )
    return _question_result(question)


def update_question_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    question_id: uuid.UUID,
    payload: InterviewQuestionUpdateRequest,
    correlation_id: str,
) -> InterviewQuestionResult:
    """Edita/reordena/aprueba; revalida políticas si cambia el texto y versiona."""
    _authorize_write(db, organization_id, actor_id, actor_role)
    question = _require_question(db, organization_id, question_id)
    guide = _require_guide(db, organization_id, question.guide_id)
    text_changed = any(
        value is not None
        for value in (payload.question, payload.evidence_focus, payload.competency)
    )
    if text_changed:
        _validate_question_policy(
            db,
            organization_id,
            guide,
            _draft_from_question(
                question,
                question_text=payload.question,
                evidence_focus=payload.evidence_focus,
                competency=payload.competency,
            ),
        )

    if payload.question is not None:
        question.question = payload.question
    if payload.evidence_focus is not None:
        question.evidence_focus = payload.evidence_focus
    if payload.competency is not None:
        question.competency = payload.competency
    if payload.position is not None:
        question.position = payload.position
    if payload.status is not None and payload.status is not question.status:
        question.transition_to(payload.status)
    if question.status is InterviewQuestionStatus.APPROVED or (
        text_changed and question.status is not InterviewQuestionStatus.REJECTED
    ):
        question.review_required = False

    try:
        _record_guide_change(db, organization_id, guide, actor_id=actor_id)
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="interview.question_updated",
            resource_type=_QUESTION_RESOURCE_TYPE,
            resource_id=question.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise InterviewGenerationError("position_conflict") from None
    except SQLAlchemyError:
        db.rollback()
        raise
    _log_api_event(
        "interview.question_updated",
        organization_id=organization_id,
        resource_id=question.id,
        result=question.status.value,
        correlation_id=correlation_id,
    )
    return _question_result(question)


def archive_question_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    question_id: uuid.UUID,
    correlation_id: str,
) -> InterviewQuestionResult:
    """Soft delete: solo cambia el estado; la fila y su historial permanecen."""
    _authorize_write(db, organization_id, actor_id, actor_role)
    question = _require_question(db, organization_id, question_id)
    guide = _require_guide(db, organization_id, question.guide_id)
    if question.status is InterviewQuestionStatus.ARCHIVED:
        return _question_result(question)
    question.transition_to(InterviewQuestionStatus.ARCHIVED)
    question.review_required = False
    try:
        _record_guide_change(db, organization_id, guide, actor_id=actor_id)
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="interview.question_archived",
            resource_type=_QUESTION_RESOURCE_TYPE,
            resource_id=question.id,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    _log_api_event(
        "interview.question_archived",
        organization_id=organization_id,
        resource_id=question.id,
        result=InterviewQuestionStatus.ARCHIVED.value,
        correlation_id=correlation_id,
    )
    return _question_result(question)


def _feedback_result(
    feedback: InterviewFeedback, question: InterviewQuestion
) -> InterviewFeedbackResult:
    return InterviewFeedbackResult(
        id=feedback.id,
        question_id=feedback.question_id,
        requirement_id=question.requirement_id,
        interviewer_id=feedback.interviewer_id,
        status=feedback.status,
        observed_evidence=list(feedback.observed_evidence),
        gaps=list(feedback.gaps),
        follow_up_needed=feedback.follow_up_needed,
        notes=feedback.notes,
        submitted_at=feedback.submitted_at,
        created_at=feedback.created_at,
    )


def submit_feedback_for_api(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: MembershipRole,
    question_id: uuid.UUID,
    payload: InterviewFeedbackSubmitRequest,
    correlation_id: str,
) -> InterviewFeedbackResult:
    """Registra observación humana; actor y tenant vienen de la sesión."""
    _authorize_write(db, organization_id, actor_id, actor_role)
    question = _require_question(db, organization_id, question_id)
    guide = _require_guide(db, organization_id, question.guide_id)
    feedback = InterviewFeedback(
        organization_id=organization_id,
        question_id=question.id,
        guide_id=guide.id,
        application_id=guide.application_id,
        interviewer_id=actor_id,
        status=InterviewFeedbackStatus.PENDING,
        observed_evidence=list(payload.observed_evidence),
        gaps=list(payload.gaps),
        follow_up_needed=payload.follow_up_needed,
        notes=payload.notes,
    )
    feedback.transition_to(InterviewFeedbackStatus.SUBMITTED, datetime.now(UTC))
    try:
        db.add(feedback)
        db.flush()
        record_audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            action="interview.feedback_submitted",
            resource_type=_FEEDBACK_RESOURCE_TYPE,
            resource_id=feedback.id,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    _log_api_event(
        "interview.feedback_submitted",
        organization_id=organization_id,
        resource_id=feedback.id,
        result=InterviewFeedbackStatus.SUBMITTED.value,
        correlation_id=correlation_id,
    )
    return _feedback_result(feedback, question)


def list_feedback_for_api(
    db: DBSession,
    organization_id: uuid.UUID,
    question_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> InterviewFeedbackListResponse:
    """Historial de feedback del tenant para una pregunta propia."""
    question = _require_question(db, organization_id, question_id)
    rows = list_feedback(
        db, organization_id, question_id=question.id, limit=limit, offset=offset
    )
    return InterviewFeedbackListResponse(
        items=[_feedback_result(row, question) for row in rows],
        total=count_feedback(db, organization_id, question_id=question.id),
        limit=limit,
        offset=offset,
    )
