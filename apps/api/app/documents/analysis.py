from __future__ import annotations

import logging
import uuid

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.agents.cv_analyst import (
    PROMPT_VERSION,
    AgentToolError,
    AnalysisContext,
    get_confirmed_document_text,
)
from app.agents.extraction_schema import (
    EvidenceRef,
    ExtractedFieldPayload,
    ExtractedProfile,
    FieldName,
    FieldStatus,
)
from app.core.logging import log_structured
from app.documents.models import (
    DocumentExtraction,
    ExtractedField,
    ExtractedFieldName,
    ExtractedFieldStatus,
)
from app.llm.provider import ProviderError
from app.llm.registry import get_llm_provider


def _log_event(
    level: int,
    event: str,
    *,
    organization_id: uuid.UUID | str,
    document_id: uuid.UUID | str,
    result: str,
    error_code: str | None = None,
    review_required: bool | None = None,
    detail: str = "",
) -> None:
    """Logs con IDs, prompt y códigos; nunca CV, evidencia citada ni chain-of-thought."""
    message = (
        f"{event} organization_id={organization_id} document_id={document_id} "
        f"prompt_version={PROMPT_VERSION} result={result}"
    )
    if error_code:
        message += f" error_code={error_code}"
    if review_required is not None:
        message += f" review_required={str(review_required).lower()}"
    if detail:
        message += f" detail={detail}"
    log_structured(level, message, organization_id=str(organization_id))


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def _ref_is_valid(
    ref: EvidenceRef, document_id: uuid.UUID, page_texts: dict[int, str]
) -> bool:
    if ref.document_id != document_id:
        return False
    text = page_texts.get(ref.page)
    if text is None or ref.quote not in text:
        return False
    return ref.offset is None or text.find(ref.quote) == ref.offset


def _ref_to_json(ref: EvidenceRef) -> dict[str, object]:
    result: dict[str, object] = {
        "document_id": str(ref.document_id),
        "page": ref.page,
        "quote": ref.quote,
    }
    if ref.offset is not None:
        result["offset"] = ref.offset
    return result


def _model_field_name(name: FieldName) -> ExtractedFieldName:
    return ExtractedFieldName(name.value)


def _model_status(status: FieldStatus) -> ExtractedFieldStatus:
    if status is FieldStatus.EXTRACTED:
        return ExtractedFieldStatus.EXTRACTED
    if status is FieldStatus.NEEDS_REVIEW:
        return ExtractedFieldStatus.NEEDS_REVIEW
    return ExtractedFieldStatus.MISSING


def analyze_extraction(
    db: DBSession,
    organization_id: uuid.UUID | str,
    document_id: uuid.UUID | str,
    extraction: DocumentExtraction,
) -> None:
    """Analiza una extracción propia, verifica evidencias y persiste campos sin confirmar."""
    try:
        tenant = _as_uuid(organization_id)
        doc_id = _as_uuid(document_id)
    except (TypeError, ValueError):
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=organization_id,
            document_id=document_id,
            result="aborted",
            error_code="invalid_context",
        )
        return

    if extraction.document_id != doc_id:
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=tenant,
            document_id=doc_id,
            result="aborted",
            error_code="organization_mismatch",
        )
        return

    try:
        pages = get_confirmed_document_text(db, tenant, doc_id, extraction)
    except AgentToolError as exc:
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=tenant,
            document_id=doc_id,
            result="aborted",
            error_code=exc.code,
        )
        return

    existing = db.scalar(
        select(func.count())
        .select_from(ExtractedField)
        .where(ExtractedField.extraction_id == extraction.id)
    )
    if existing:
        _log_event(
            logging.INFO,
            "cv_analysis_duplicate",
            organization_id=tenant,
            document_id=doc_id,
            result="skipped",
        )
        return

    context = AnalysisContext(
        document_id=doc_id,
        organization_id=tenant,
        pages=pages,
        truncated=len(extraction.pages) > len(pages),
    )
    try:
        raw = get_llm_provider().generate_structured_output(
            PROMPT_VERSION, ExtractedProfile, context.as_provider_mapping()
        )
    except ProviderError as exc:
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=tenant,
            document_id=doc_id,
            result="failed",
            error_code=exc.code,
        )
        return
    except (TypeError, ValueError):
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=tenant,
            document_id=doc_id,
            result="failed",
            error_code="invalid_provider_output",
        )
        return

    try:
        profile = ExtractedProfile.model_validate(raw)
    except ValidationError:
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=tenant,
            document_id=doc_id,
            result="failed",
            error_code="invalid_provider_output",
        )
        return

    if profile.prompt_version != PROMPT_VERSION:
        _log_event(
            logging.WARNING,
            "cv_analysis_failed",
            organization_id=tenant,
            document_id=doc_id,
            result="failed",
            error_code="prompt_version_mismatch",
        )
        return

    page_texts = {page.page: page.text for page in pages}
    injection_refs = [
        ref
        for ref in profile.prompt_injection_evidence
        if _ref_is_valid(ref, doc_id, page_texts)
    ]
    injection_pages = {ref.page for ref in injection_refs}
    has_injection = profile.prompt_injection_detected

    by_name = {payload.field_name: payload for payload in profile.fields}
    missing_payload = ExtractedFieldPayload(
        field_name=FieldName.NAME,
        value=None,
        status=FieldStatus.MISSING,
        evidence_refs=[],
    )

    rows: list[ExtractedField] = []
    missing_count = 0
    review_count = 0
    invalid_evidence = False
    for field in FieldName:
        payload = by_name.get(field) or missing_payload.model_copy(
            update={"field_name": field}
        )
        valid_refs = [
            ref for ref in payload.evidence_refs if _ref_is_valid(ref, doc_id, page_texts)
        ]
        if len(valid_refs) != len(payload.evidence_refs):
            invalid_evidence = True

        status = payload.status
        value = payload.value
        if status is FieldStatus.MISSING:
            value = None
            evidence: list[dict[str, object]] = []
            missing_count += 1
        elif status is FieldStatus.EXTRACTED and (
            value in (None, "", []) or not valid_refs
        ):
            status = FieldStatus.NEEDS_REVIEW
            evidence = []
        elif not valid_refs:
            status = FieldStatus.NEEDS_REVIEW
            evidence = []
        else:
            evidence = [_ref_to_json(ref) for ref in valid_refs]
            if status is FieldStatus.EXTRACTED and any(
                ref.page in injection_pages for ref in valid_refs
            ):
                status = FieldStatus.NEEDS_REVIEW

        if status is FieldStatus.NEEDS_REVIEW:
            review_count += 1
            if not valid_refs:
                evidence = []
        elif status is FieldStatus.EXTRACTED:
            evidence = [_ref_to_json(ref) for ref in valid_refs]

        rows.append(
            ExtractedField(
                id=uuid.uuid4(),
                extraction_id=extraction.id,
                field_name=_model_field_name(field),
                value=value,
                status=_model_status(status),
                evidence=evidence,
                confirmed_by=None,
                confirmed_at=None,
            )
        )

    review_required = (
        profile.review_required
        or has_injection
        or missing_count > 0
        or review_count > 0
        or invalid_evidence
        or context.truncated
    )
    limitation_codes = list(profile.limitations)
    if context.truncated:
        limitation_codes.append("context_truncated")
    if invalid_evidence:
        limitation_codes.append("invalid_evidence_dropped")
    if has_injection and not injection_refs:
        limitation_codes.append("prompt_injection_evidence_invalid")

    # Señales de control persistentes: la revisión humana las consume desde la API.
    extraction.injection_detected = has_injection
    extraction.review_required = review_required or has_injection

    db.add_all(rows)
    db.commit()

    result = "review_required" if review_required else "completed"
    _log_event(
        logging.INFO,
        "cv_analysis_completed" if not review_required else "cv_analysis_review_required",
        organization_id=tenant,
        document_id=doc_id,
        result=result,
        review_required=review_required,
        detail=(
            f"fields={len(rows)} missing={missing_count} needs_review={review_count} "
            f"limitations={','.join(sorted(set(limitation_codes)))}"
        ),
    )
    if has_injection:
        _log_event(
            logging.WARNING,
            "cv_analysis_prompt_injection_detected",
            organization_id=tenant,
            document_id=doc_id,
            result="flagged",
        )
