"""Registry y herramientas acotadas del runtime de agentes (SDD §10, ADR-006).

Ninguna tool ejecuta SQL libre, shell ni filesystem. Todas verifican membresía
activa, pertenencia del recurso al tenant, permiso por rol, límite de llamadas,
timeout, idempotencia y traza sin CV ni secretos en cada invocación.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import NoReturn

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session as DBSession

from app.agents.models import (
    AgentDomainError,
    AgentEventType,
    AgentRun,
    ApprovalStatus,
)
from app.agents.repositories import (
    count_tool_invocations,
    create_agent_event,
    create_approval,
    find_approval_by_payload_hash,
    find_tool_event_by_hash,
    get_agent_run,
)
from app.agents.tool_schemas import (
    ApprovalRequestResult,
    AssessmentDraftResult,
    CandidateProfileResult,
    ConfirmedDocumentTextResult,
    ConfirmedField,
    ConfirmedQuote,
    CreateAssessmentDraftInput,
    CreateMessageDraftInput,
    GetCandidateProfileInput,
    GetConfirmedDocumentTextInput,
    GetJobRequirementsInput,
    JobRequirementItem,
    JobRequirementsResult,
    MessageDraftResult,
    RequestHumanApprovalInput,
    StatusCount,
)
from app.applications.repositories import get_application
from app.candidates.repositories import get_candidate
from app.documents.models import (
    DocumentExtraction,
    ExtractedFieldName,
    ExtractedFieldStatus,
)
from app.documents.repositories import (
    get_document,
    get_latest_extraction,
    list_documents,
    list_fields,
)
from app.identity.models import MembershipRole, User, UserStatus
from app.identity.repositories import get_membership
from app.jobs.models import JobVersion
from app.jobs.repositories import get_job, list_versions

_MAX_FIELDS = 20
_MAX_QUOTES = 20
_MAX_VALUE_CHARS = 500
_MAX_QUOTE_CHARS = 400
_MAX_DOCUMENTS = 10
_TERMINAL_STATUSES = frozenset(
    {ExtractedFieldStatus.CONFIRMED, ExtractedFieldStatus.CORRECTED}
)


class ToolErrorCode(StrEnum):
    """Códigos estables; el mensaje nunca incluye datos del recurso."""

    UNKNOWN_TOOL = "unknown_tool"
    DUPLICATE_TOOL = "duplicate_tool"
    WORKFLOW_NOT_ALLOWED = "workflow_not_allowed"
    PERMISSION_DENIED = "permission_denied"
    INVALID_INPUT = "invalid_input"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    TENANT_MISMATCH = "tenant_mismatch"


_ERROR_MESSAGES: dict[ToolErrorCode, str] = {
    ToolErrorCode.UNKNOWN_TOOL: "Herramienta no disponible",
    ToolErrorCode.DUPLICATE_TOOL: "Herramienta ya registrada",
    ToolErrorCode.WORKFLOW_NOT_ALLOWED: "Herramienta no permitida para el flujo",
    ToolErrorCode.PERMISSION_DENIED: "Permiso insuficiente",
    ToolErrorCode.INVALID_INPUT: "Entrada inválida",
    ToolErrorCode.RATE_LIMITED: "Límite de invocaciones alcanzado",
    ToolErrorCode.TIMEOUT: "Tiempo de ejecución excedido",
    ToolErrorCode.TENANT_MISMATCH: "Recurso no disponible para la organización",
}


class ToolInvocationError(AgentDomainError):
    """Error determinista de una tool; `code` es la única información pública."""

    def __init__(self, code: ToolErrorCode) -> None:
        super().__init__(_ERROR_MESSAGES[code])
        self.code = code


@dataclass(frozen=True)
class ToolContext:
    """Contexto autorizado de la ejecución; el tenant nunca viene del documento."""

    db: DBSession
    organization_id: uuid.UUID
    actor_id: uuid.UUID
    actor_role: MembershipRole
    agent_run_id: uuid.UUID
    correlation_id: uuid.UUID
    idempotency_key: str


@dataclass
class ToolInvocation:
    """Estado local de una llamada; `result_id` se reutiliza en reintentos."""

    idempotency_hash: str
    result_id: uuid.UUID | None = None
    result_payload: dict[str, object] = field(default_factory=dict)
    is_retry: bool = False


ToolHandler = Callable[[ToolContext, BaseModel, ToolInvocation], BaseModel]


@dataclass(frozen=True)
class ToolDefinition:
    """Contrato ejecutable: permisos, flujos, límite, timeout y tipo de efecto."""

    name: str
    handler: ToolHandler
    input_schema: type[BaseModel]
    allowed_workflows: frozenset[str]
    roles: frozenset[MembershipRole]
    timeout_seconds: float
    max_calls_per_run: int
    is_write: bool


def _fail(code: ToolErrorCode) -> NoReturn:
    raise ToolInvocationError(code)


def _bounded_text(value: object, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (list, tuple)):
        text = ", ".join(str(item) for item in value)
    elif isinstance(value, Mapping):
        text = ", ".join(str(part) for part in value.values())
    else:
        text = str(value)
    return text.strip()[:limit]


def _page_texts(extraction: DocumentExtraction) -> dict[int, str]:
    result: dict[int, str] = {}
    raw_pages: object = extraction.pages
    if not isinstance(raw_pages, (list, tuple)):
        return result
    for item in raw_pages:
        if not isinstance(item, Mapping):
            continue
        page = item.get("page")
        text = item.get("text")
        if isinstance(page, int) and page > 0 and isinstance(text, str):
            result[page] = text[:4000]
    return result


def _confirmed_quote(
    raw: object,
    *,
    document_id: uuid.UUID,
    field_name: ExtractedFieldName,
    page_texts: dict[int, str],
) -> ConfirmedQuote | None:
    """Cita verificada contra texto confirmado; el contenido sigue siendo dato."""
    if not isinstance(raw, Mapping):
        return None
    raw_document_id = raw.get("document_id")
    page = raw.get("page")
    if not isinstance(raw_document_id, str) or not isinstance(page, int):
        return None
    try:
        cited_document = uuid.UUID(raw_document_id)
    except ValueError:
        return None
    if cited_document != document_id or page < 1:
        return None
    page_text = page_texts.get(page)
    raw_quote = raw.get("quote")
    if page_text is None or not isinstance(raw_quote, str):
        return None
    quote = raw_quote.strip()[:_MAX_QUOTE_CHARS]
    if not quote or quote not in page_text:
        return None
    offset = raw.get("offset")
    if offset is not None and (
        not isinstance(offset, int) or page_text.find(quote) != offset
    ):
        return None
    return ConfirmedQuote(
        document_id=document_id,
        field_name=field_name,
        page=page,
        quote=quote,
        offset=offset if isinstance(offset, int) else None,
    )


def _collect_confirmed(
    ctx: ToolContext,
    *,
    document_id: uuid.UUID | None = None,
    field_name: ExtractedFieldName | None = None,
    candidate_id: uuid.UUID | None = None,
) -> tuple[list[ConfirmedField], list[ConfirmedQuote]]:
    """Campos confirmados/corregidos y citas acotadas del tenant, sin CV completo."""
    if document_id is not None:
        document = get_document(ctx.db, ctx.organization_id, document_id)
        if document is None:
            _fail(ToolErrorCode.TENANT_MISMATCH)
        documents = [document]
    else:
        documents = list_documents(
            ctx.db, ctx.organization_id, candidate_id=candidate_id, limit=_MAX_DOCUMENTS
        )

    fields: list[ConfirmedField] = []
    quotes: list[ConfirmedQuote] = []
    for document in documents:
        if document.organization_id != ctx.organization_id:
            continue
        if candidate_id is not None and document.candidate_id != candidate_id:
            continue
        extraction = get_latest_extraction(ctx.db, ctx.organization_id, document.id)
        if extraction is None or extraction.document_id != document.id:
            continue
        page_texts = _page_texts(extraction)
        for extracted_field in list_fields(
            ctx.db, ctx.organization_id, document.id, extraction.id
        ):
            if extracted_field.status not in _TERMINAL_STATUSES:
                continue
            if field_name is not None and extracted_field.field_name != field_name:
                continue
            if len(fields) >= _MAX_FIELDS:
                break
            fields.append(
                ConfirmedField(
                    field_name=extracted_field.field_name,
                    value=_bounded_text(extracted_field.value, _MAX_VALUE_CHARS),
                    document_id=document.id,
                    status=extracted_field.status.value,
                )
            )
            raw_evidence: object = extracted_field.evidence
            if not isinstance(raw_evidence, (list, tuple)):
                continue
            for raw in raw_evidence:
                if len(quotes) >= _MAX_QUOTES:
                    break
                quote = _confirmed_quote(
                    raw,
                    document_id=document.id,
                    field_name=extracted_field.field_name,
                    page_texts=page_texts,
                )
                if quote is not None:
                    quotes.append(quote)
    return fields, quotes


def _stable_result_id(invocation: ToolInvocation) -> uuid.UUID:
    """ID derivado de la idempotencia; reintentos devuelven el mismo valor."""
    if invocation.result_id is None:
        invocation.result_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"talentos:tool:{invocation.idempotency_hash}"
        )
    return invocation.result_id


def _canonical_args(args: BaseModel) -> str:
    return json.dumps(
        args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _idempotency_hash(ctx: ToolContext, tool_name: str, args: BaseModel) -> str:
    material = f"{ctx.idempotency_key}\n{tool_name}\n{_canonical_args(args)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _cached_result_id(event_payload: Mapping[str, object]) -> uuid.UUID | None:
    raw = event_payload.get("draft_id") or event_payload.get("approval_id")
    if not isinstance(raw, str):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Handlers: solo services/repositorios, sin SQL libre, shell ni filesystem.
# ---------------------------------------------------------------------------


def _get_job_requirements(
    ctx: ToolContext, args: BaseModel, _invocation: ToolInvocation
) -> BaseModel:
    assert isinstance(args, GetJobRequirementsInput)
    if get_job(ctx.db, ctx.organization_id, args.job_id) is None:
        _fail(ToolErrorCode.TENANT_MISMATCH)
    versions = list_versions(ctx.db, ctx.organization_id, args.job_id)
    if not versions:
        _fail(ToolErrorCode.TENANT_MISMATCH)
    version: JobVersion | None
    if args.job_version_id is None:
        version = max(versions, key=lambda item: item.version)
    else:
        version = next((item for item in versions if item.id == args.job_version_id), None)
        if version is None:
            _fail(ToolErrorCode.TENANT_MISMATCH)
    raw_requirements = version.snapshot.get("requirements")
    requirements: list[JobRequirementItem] = []
    if isinstance(raw_requirements, (list, tuple)):
        for raw in raw_requirements:
            if len(requirements) >= 20 or not isinstance(raw, Mapping):
                break
            raw_id = raw.get("id")
            if not isinstance(raw_id, str):
                continue
            try:
                requirement_id = uuid.UUID(raw_id)
            except ValueError:
                continue
            description = _bounded_text(raw.get("description"), 1000)
            if not description:
                continue
            requirements.append(
                JobRequirementItem(
                    requirement_id=requirement_id,
                    description=description,
                    category=_bounded_text(raw.get("category"), 50) or "other",
                    importance=_bounded_text(raw.get("importance"), 50) or "required",
                    expected_level=_bounded_text(raw.get("expected_level"), 100) or None,
                )
            )
    return JobRequirementsResult(
        job_id=args.job_id,
        job_version_id=version.id,
        version=version.version,
        requirements=requirements,
        missing=["requirements_missing"] if not requirements else [],
    )


def _get_candidate_profile(
    ctx: ToolContext, args: BaseModel, _invocation: ToolInvocation
) -> BaseModel:
    assert isinstance(args, GetCandidateProfileInput)
    candidate = get_candidate(ctx.db, ctx.organization_id, args.candidate_id)
    if candidate is None:
        _fail(ToolErrorCode.TENANT_MISMATCH)
    fields, quotes = _collect_confirmed(ctx, candidate_id=candidate.id)
    missing: list[str] = []
    if not fields:
        missing.append("no_confirmed_fields")
    elif not quotes:
        missing.append("no_confirmed_evidence")
    return CandidateProfileResult(
        candidate_id=candidate.id,
        profile_status=candidate.profile_status,
        fields=fields,
        evidence=quotes,
        missing=missing,
    )


def _get_confirmed_document_text(
    ctx: ToolContext, args: BaseModel, _invocation: ToolInvocation
) -> BaseModel:
    assert isinstance(args, GetConfirmedDocumentTextInput)
    _, quotes = _collect_confirmed(
        ctx,
        document_id=args.document_id,
        field_name=args.field_name,
    )
    if args.field_name is None:
        selected = quotes
    else:
        selected = [quote for quote in quotes if quote.field_name == args.field_name]
    return ConfirmedDocumentTextResult(
        document_id=args.document_id,
        field_name=args.field_name,
        quotes=selected[: args.limit],
        missing=["no_confirmed_text"] if not selected else [],
    )


def _create_assessment_draft(
    ctx: ToolContext, args: BaseModel, invocation: ToolInvocation
) -> BaseModel:
    assert isinstance(args, CreateAssessmentDraftInput)
    application = get_application(ctx.db, ctx.organization_id, args.application_id)
    if application is None:
        _fail(ToolErrorCode.TENANT_MISMATCH)
    for evaluation in args.result.evaluations:
        for ref in evaluation.evidence_refs:
            document = get_document(ctx.db, ctx.organization_id, ref.document_id)
            if document is None or document.candidate_id != application.candidate_id:
                _fail(ToolErrorCode.TENANT_MISMATCH)

    draft_id = _stable_result_id(invocation)
    counts = Counter(item.status for item in args.result.evaluations)
    summary = [
        StatusCount(status=status, count=count)
        for status, count in sorted(counts.items(), key=lambda item: item[0].value)
    ]
    invocation.result_payload = {
        "draft_id": str(draft_id),
        "statuses_summary": [item.model_dump(mode="json") for item in summary],
    }
    return AssessmentDraftResult(
        draft_id=draft_id,
        application_id=args.application_id,
        statuses_summary=summary,
        review_required=args.result.review_required,
        model_version=args.result.model_version,
        prompt_version=args.result.prompt_version,
    )


def _render_message(
    template: str, topic: str, call_to_action: str, language: str
) -> str:
    if language == "es":
        bodies = {
            "initial_contact": f"Hola, comentarte una oportunidad sobre {topic}.",
            "interview_invite": f"Hola, nos gustaría conversar sobre {topic} en una entrevista.",
            "follow_up": f"Hola, hacemos seguimiento de la conversación sobre {topic}.",
        }
        closing = f"Si te parece bien, {call_to_action}."
    else:
        bodies = {
            "initial_contact": f"Hello, we would like to share an opportunity about {topic}.",
            "interview_invite": f"Hello, we would like to discuss {topic} in an interview.",
            "follow_up": f"Hello, following up on our conversation about {topic}.",
        }
        closing = f"If that works, {call_to_action}."
    return f"{bodies[template]} {closing}"[:500]


def _create_message_draft(
    ctx: ToolContext, args: BaseModel, invocation: ToolInvocation
) -> BaseModel:
    assert isinstance(args, CreateMessageDraftInput)
    if get_candidate(ctx.db, ctx.organization_id, args.candidate_id) is None:
        _fail(ToolErrorCode.TENANT_MISMATCH)
    draft_id = _stable_result_id(invocation)
    template = args.template_data.template
    text = _render_message(
        template.value,
        args.template_data.topic,
        args.template_data.call_to_action,
        args.template_data.language,
    )
    invocation.result_payload = {
        "draft_id": str(draft_id),
        "template": template.value,
        "char_count": len(text),
    }
    return MessageDraftResult(
        draft_id=draft_id,
        candidate_id=args.candidate_id,
        template=template,
        language=args.template_data.language,
        text=text,
        char_count=len(text),
    )


def _request_human_approval(
    ctx: ToolContext, args: BaseModel, invocation: ToolInvocation
) -> BaseModel:
    assert isinstance(args, RequestHumanApprovalInput)
    existing = find_approval_by_payload_hash(
        ctx.db,
        ctx.organization_id,
        ctx.agent_run_id,
        invocation.idempotency_hash,
    )
    if existing is not None:
        invocation.is_retry = True
        approval_id: uuid.UUID | None = existing.id
    else:
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            **args.payload.model_dump(mode="json"),
            "requested_by": str(ctx.actor_id),
            "requested_at": now.isoformat(),
            "idempotency_hash": invocation.idempotency_hash,
        }
        approval = create_approval(
            ctx.db,
            organization_id=ctx.organization_id,
            agent_run_id=ctx.agent_run_id,
            action_type=args.action_type.value,
            payload=payload,
        )
        approval_id = approval.id
        create_agent_event(
            ctx.db,
            organization_id=ctx.organization_id,
            agent_run_id=ctx.agent_run_id,
            event_type=AgentEventType.APPROVAL_REQUESTED,
            payload={
                "approval_id": str(approval_id),
                "action_type": args.action_type.value,
                "organization_id": str(ctx.organization_id),
                "correlation_id": str(ctx.correlation_id),
            },
            correlation_id=ctx.correlation_id,
        )
    invocation.result_id = approval_id
    if approval_id is None:
        _fail(ToolErrorCode.INVALID_INPUT)
    invocation.result_payload = {
        "approval_id": str(approval_id),
        "action_type": args.action_type.value,
    }
    return ApprovalRequestResult(
        approval_id=approval_id,
        action_type=args.action_type,
        status=ApprovalStatus.PENDING,
        requested_by=ctx.actor_id,
        requested_at=datetime.now(UTC),
        agent_run_id=ctx.agent_run_id,
    )


def _find_cached_event(
    ctx: ToolContext, name: str, invocation: ToolInvocation
) -> bool:
    event = find_tool_event_by_hash(
        ctx.db, ctx.organization_id, ctx.agent_run_id, name, invocation.idempotency_hash
    )
    if event is None:
        return False
    invocation.is_retry = True
    invocation.result_id = _cached_result_id(event.payload)
    invocation.result_payload = {
        key: value
        for key, value in event.payload.items()
        if key in {"draft_id", "approval_id", "statuses_summary", "action_type"}
    }
    if event.payload.get("status") == "failed":
        invocation.result_id = None
        return False
    return True


def _authorize(ctx: ToolContext, definition: ToolDefinition) -> None:
    """Membresía activa y rol reales en cada llamada; `actor_role` no es autoridad."""
    membership = get_membership(ctx.db, ctx.actor_id, ctx.organization_id)
    user = ctx.db.get(User, ctx.actor_id)
    if membership is None or user is None or user.status is not UserStatus.ACTIVE:
        _fail(ToolErrorCode.PERMISSION_DENIED)
    if membership.role != ctx.actor_role or membership.role not in definition.roles:
        _fail(ToolErrorCode.PERMISSION_DENIED)


class ToolRegistry:
    """Registro acotado: una tool no puede ampliar sus permisos desde un documento."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            _fail(ToolErrorCode.DUPLICATE_TOOL)
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        definition = self._definitions.get(name)
        if definition is None:
            _fail(ToolErrorCode.UNKNOWN_TOOL)
        return definition

    def names(self) -> frozenset[str]:
        return frozenset(self._definitions)

    def invoke(self, ctx: ToolContext, name: str, args: object) -> BaseModel:
        started = monotonic()
        ended: float | None = None
        definition: ToolDefinition | None = None
        run: AgentRun | None = None
        invocation: ToolInvocation | None = None
        try:
            definition = self.get(name)
            if not ctx.idempotency_key.strip():
                _fail(ToolErrorCode.INVALID_INPUT)
            run = get_agent_run(ctx.db, ctx.organization_id, ctx.agent_run_id)
            if run is None:
                _fail(ToolErrorCode.TENANT_MISMATCH)
            if run.workflow not in definition.allowed_workflows:
                _fail(ToolErrorCode.WORKFLOW_NOT_ALLOWED)
            _authorize(ctx, definition)
            try:
                validated = definition.input_schema.model_validate(args)
            except ValidationError:
                _fail(ToolErrorCode.INVALID_INPUT)
            invocation = ToolInvocation(_idempotency_hash(ctx, name, validated))
            if definition.is_write and _find_cached_event(ctx, name, invocation):
                return definition.handler(ctx, validated, invocation)
            used = count_tool_invocations(
                ctx.db, ctx.organization_id, ctx.agent_run_id, name
            )
            if used >= definition.max_calls_per_run:
                _fail(ToolErrorCode.RATE_LIMITED)
            result = definition.handler(ctx, validated, invocation)
            ended = monotonic()
            duration_ms = max(0, int((ended - started) * 1000))
            if duration_ms > definition.timeout_seconds * 1000:
                _fail(ToolErrorCode.TIMEOUT)
            self._record(ctx, name, "succeeded", duration_ms, "", invocation)
            return result
        except ToolInvocationError as exc:
            if definition is not None and run is not None and invocation is not None:
                if ended is None:
                    ended = monotonic()
                duration_ms = max(0, int((ended - started) * 1000))
                self._record(ctx, name, "failed", duration_ms, exc.code.value, invocation)
            raise

    def _record(
        self,
        ctx: ToolContext,
        name: str,
        status: str,
        duration_ms: int,
        error_type: str,
        invocation: ToolInvocation,
    ) -> None:
        payload: dict[str, object] = {
            "tool": name,
            "status": status,
            "duration_ms": duration_ms,
            "error_type": error_type,
            "organization_id": str(ctx.organization_id),
            "correlation_id": str(ctx.correlation_id),
            "idempotency_hash": invocation.idempotency_hash,
        }
        payload.update(invocation.result_payload)
        create_agent_event(
            ctx.db,
            organization_id=ctx.organization_id,
            agent_run_id=ctx.agent_run_id,
            event_type=AgentEventType.TOOL_INVOKED,
            payload=payload,
            correlation_id=ctx.correlation_id,
        )


_READ_WORKFLOWS = frozenset(
    {"job_analysis", "cv_analysis", "matching", "quality_audit", "orchestration"}
)
_DRAFT_WORKFLOWS = frozenset({"matching", "workflow_assistant", "orchestration"})
_ALL_ROLES = frozenset(set(MembershipRole))
_WRITE_ROLES = frozenset(
    {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.RECRUITER}
)


def build_default_registry() -> ToolRegistry:
    """Seis tools del MVP: lectura acotada, borradores y aprobación humana."""
    registry = ToolRegistry()
    definitions = (
        ToolDefinition(
            name="get_job_requirements",
            handler=_get_job_requirements,
            input_schema=GetJobRequirementsInput,
            allowed_workflows=_READ_WORKFLOWS,
            roles=_ALL_ROLES,
            timeout_seconds=2.0,
            max_calls_per_run=20,
            is_write=False,
        ),
        ToolDefinition(
            name="get_candidate_profile",
            handler=_get_candidate_profile,
            input_schema=GetCandidateProfileInput,
            allowed_workflows=_READ_WORKFLOWS,
            roles=_ALL_ROLES,
            timeout_seconds=2.0,
            max_calls_per_run=20,
            is_write=False,
        ),
        ToolDefinition(
            name="get_confirmed_document_text",
            handler=_get_confirmed_document_text,
            input_schema=GetConfirmedDocumentTextInput,
            allowed_workflows=_READ_WORKFLOWS,
            roles=_ALL_ROLES,
            timeout_seconds=2.0,
            max_calls_per_run=20,
            is_write=False,
        ),
        ToolDefinition(
            name="create_assessment_draft",
            handler=_create_assessment_draft,
            input_schema=CreateAssessmentDraftInput,
            allowed_workflows=_DRAFT_WORKFLOWS,
            roles=_WRITE_ROLES,
            timeout_seconds=2.0,
            max_calls_per_run=5,
            is_write=True,
        ),
        ToolDefinition(
            name="create_message_draft",
            handler=_create_message_draft,
            input_schema=CreateMessageDraftInput,
            allowed_workflows=_DRAFT_WORKFLOWS,
            roles=_WRITE_ROLES,
            timeout_seconds=2.0,
            max_calls_per_run=5,
            is_write=True,
        ),
        ToolDefinition(
            name="request_human_approval",
            handler=_request_human_approval,
            input_schema=RequestHumanApprovalInput,
            allowed_workflows=_DRAFT_WORKFLOWS,
            roles=_WRITE_ROLES,
            timeout_seconds=2.0,
            max_calls_per_run=5,
            is_write=True,
        ),
    )
    for definition in definitions:
        registry.register(definition)
    return registry
