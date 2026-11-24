from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import cast

from sqlalchemy.orm import Session as DBSession

from app.applications.models import Application
from app.applications.repositories import get_application
from app.candidates.models import Candidate
from app.candidates.repositories import get_candidate
from app.documents.models import (
    DocumentExtraction,
    ExtractedFieldStatus,
)
from app.documents.repositories import (
    get_document,
    get_latest_extraction,
    list_documents,
    list_fields,
)
from app.jobs.models import Job, JobVersion
from app.jobs.repositories import get_job, list_versions

CONFIRMED_STATUSES = frozenset(
    {ExtractedFieldStatus.CONFIRMED, ExtractedFieldStatus.CORRECTED}
)
MAX_DOCUMENTS = 10
MAX_REQUIREMENTS = 20
MAX_FIELDS = 20
MAX_EVIDENCE_REFS = 20
MAX_VALUE_CHARS = 500
MAX_QUOTE_CHARS = 300
MAX_DESCRIPTION_CHARS = 1000
MAX_PAGE_CHARS = 4000


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _bounded_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (list, tuple)):
        text = ", ".join(str(item) for item in value)
    elif isinstance(value, Mapping):
        item = cast(Mapping[str, object], value)
        text = ", ".join(str(part) for part in item.values())
    else:
        text = str(value)
    return text.strip()[:MAX_VALUE_CHARS]


def _canonical_value(value: object) -> str | None:
    """Normaliza valores confirmados para detectar contradicciones sin inferir nada."""
    if isinstance(value, Mapping):
        item = cast(Mapping[str, object], value)
        if len(item) == 1 and "text" in item:
            return _canonical_value(item["text"])
        if len(item) == 1 and "items" in item:
            return _canonical_value(item["items"])
        parts = [_canonical_value(part) for part in item.values()]
        return "|".join(sorted(part for part in parts if part is not None)) or None
    if isinstance(value, str):
        return value.strip().casefold() or None
    if isinstance(value, (list, tuple)):
        parts = [_canonical_value(part) for part in value]
        return "|".join(sorted(part for part in parts if part is not None)) or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def resolve_application(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> tuple[Application, Job, Candidate, JobVersion] | None:
    """Resuelve postulación, vacante, candidato y última versión dentro del tenant."""
    application = get_application(db, organization_id, application_id)
    if application is None or application.organization_id != organization_id:
        return None
    job = get_job(db, organization_id, application.job_id)
    candidate = get_candidate(db, organization_id, application.candidate_id)
    if job is None or job.organization_id != organization_id:
        return None
    if candidate is None or candidate.organization_id != organization_id:
        return None
    versions = list_versions(db, organization_id, job.id)
    if not versions:
        return None
    version = max(versions, key=lambda item: item.version)
    if version.job_id != job.id:
        return None
    snapshot_job = version.snapshot.get("job")
    if isinstance(snapshot_job, Mapping):
        snapshot_org = cast(Mapping[str, object], snapshot_job).get("organization_id")
        if snapshot_org is not None and snapshot_org != str(organization_id):
            return None
    return application, job, candidate, version


def _requirement_from_snapshot(item: object) -> dict[str, object] | None:
    if not isinstance(item, Mapping):
        return None
    raw = cast(Mapping[str, object], item)
    raw_id = raw.get("id")
    if not isinstance(raw_id, str):
        return None
    try:
        requirement_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    description = _text(raw.get("description"), MAX_DESCRIPTION_CHARS)
    if description is None:
        return None
    return {
        "requirement_id": str(requirement_id),
        "description": description,
        "category": _text(raw.get("category"), 50) or "other",
        "importance": _text(raw.get("importance"), 50) or "required",
        "expected_level": _text(raw.get("expected_level"), 100),
    }


def load_job_requirements(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> dict[str, object]:
    """Lee requisitos del snapshot inmutable; nunca de la tabla mutable de la vacante."""
    resolved = resolve_application(db, organization_id, application_id)
    if resolved is None:
        return {
            "job_id": None,
            "job_version_id": None,
            "requirements": [],
            "missing": ["organization_mismatch"],
        }
    _, job, _, version = resolved
    raw_requirements = version.snapshot.get("requirements")
    requirements: list[dict[str, object]] = []
    if isinstance(raw_requirements, (list, tuple)):
        for item in raw_requirements:
            if len(requirements) >= MAX_REQUIREMENTS:
                break
            requirement = _requirement_from_snapshot(item)
            if requirement is not None:
                requirements.append(requirement)
    missing: list[str] = []
    if not requirements:
        missing.append("requirements_missing")
    return {
        "job_id": str(job.id),
        "job_version_id": str(version.id),
        "requirements": requirements,
        "missing": missing,
    }


def _page_texts(extraction: DocumentExtraction) -> dict[int, str]:
    result: dict[int, str] = {}
    raw_pages: object = extraction.pages
    if not isinstance(raw_pages, (list, tuple)):
        return result
    for item in raw_pages:
        if not isinstance(item, Mapping):
            continue
        page = cast(Mapping[str, object], item)
        number = page.get("page")
        text = page.get("text")
        if isinstance(number, int) and number > 0 and isinstance(text, str):
            result[number] = text[:MAX_PAGE_CHARS]
    return result


def _evidence_from_field(
    item: object,
    document_id: uuid.UUID,
    field_name: str,
    page_texts: dict[int, str],
) -> dict[str, object] | None:
    if not isinstance(item, Mapping):
        return None
    raw = cast(Mapping[str, object], item)
    raw_document_id = raw.get("document_id")
    if not isinstance(raw_document_id, str):
        return None
    try:
        cited_document = uuid.UUID(raw_document_id)
    except ValueError:
        return None
    if cited_document != document_id:
        return None
    page = raw.get("page")
    quote = _text(raw.get("quote"), MAX_QUOTE_CHARS)
    if not isinstance(page, int) or page < 1 or quote is None:
        return None
    text = page_texts.get(page)
    if text is None or quote not in text:
        return None
    offset = raw.get("offset")
    if offset is not None and (
        not isinstance(offset, int) or text.find(quote) != offset
    ):
        return None
    return {
        "document_id": str(document_id),
        "field_name": field_name,
        "page": page,
        "quote": quote,
        "offset": offset if isinstance(offset, int) else None,
    }


def load_candidate_profile(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> dict[str, object]:
    """Devuelve solo campos confirmados/corregidos y sus citas, filtrados por tenant."""
    resolved = resolve_application(db, organization_id, application_id)
    if resolved is None:
        return {
            "candidate_id": None,
            "fields": [],
            "evidence": [],
            "contradictions": [],
            "missing": ["organization_mismatch"],
        }
    _, _, candidate, _ = resolved
    documents = list_documents(
        db, organization_id, candidate_id=candidate.id, limit=MAX_DOCUMENTS
    )
    fields: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    canonical_values: dict[str, set[str]] = {}

    for document in documents:
        if document.organization_id != organization_id:
            continue
        if document.candidate_id != candidate.id:
            continue
        extraction = get_latest_extraction(db, organization_id, document.id)
        if extraction is None or extraction.document_id != document.id:
            continue
        page_texts = _page_texts(extraction)
        for field in list_fields(db, organization_id, document.id, extraction.id):
            if field.status not in CONFIRMED_STATUSES or len(fields) >= MAX_FIELDS:
                continue
            field_name = field.field_name.value
            fields.append(
                {
                    "field_name": field_name,
                    "value": _bounded_value(field.value),
                    "document_id": str(document.id),
                    "status": field.status.value,
                }
            )
            canonical = _canonical_value(field.value)
            if canonical is not None:
                canonical_values.setdefault(field_name, set()).add(canonical)
            raw_evidence: object = field.evidence
            if not isinstance(raw_evidence, (list, tuple)):
                continue
            for item in raw_evidence:
                if len(evidence) >= MAX_EVIDENCE_REFS:
                    break
                parsed = _evidence_from_field(item, document.id, field_name, page_texts)
                if parsed is not None:
                    evidence.append(parsed)

    contradictions = sorted(
        name for name, values in canonical_values.items() if len(values) > 1
    )
    missing: list[str] = []
    if not documents:
        missing.append("no_documents")
    if not fields:
        missing.append("no_confirmed_fields")
    elif not evidence:
        missing.append("no_confirmed_evidence")
    return {
        "candidate_id": str(candidate.id),
        "fields": fields,
        "evidence": evidence,
        "contradictions": contradictions,
        "missing": missing,
    }


def load_confirmed_document_text(
    db: DBSession,
    organization_id: uuid.UUID,
    application_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, object]:
    """Fragmentos confirmados de un documento propio; nunca el CV completo."""
    resolved = resolve_application(db, organization_id, application_id)
    if resolved is None:
        return {"document_id": str(document_id), "quotes": [], "missing": ["organization_mismatch"]}
    _, _, candidate, _ = resolved
    document = get_document(db, organization_id, document_id)
    if document is None or document.candidate_id != candidate.id:
        return {
            "document_id": str(document_id),
            "quotes": [],
            "missing": ["organization_mismatch"],
        }
    profile = load_candidate_profile(db, organization_id, application_id)
    all_evidence = cast(list[dict[str, object]], profile["evidence"])
    quotes = [
        item for item in all_evidence if item["document_id"] == str(document_id)
    ]
    missing: list[str] = []
    if not quotes:
        missing.append("no_confirmed_text")
    return {
        "document_id": str(document_id),
        "quotes": quotes,
        "missing": missing,
    }


def build_context(
    db: DBSession, organization_id: uuid.UUID, application_id: uuid.UUID
) -> dict[str, object]:
    """Contexto mínimo del tenant: versión inmutable y campos confirmados delimitados."""
    resolved = resolve_application(db, organization_id, application_id)
    if resolved is None:
        return {
            "organization_id": str(organization_id),
            "application_id": str(application_id),
            "candidate_id": None,
            "job_id": None,
            "job_version_id": None,
            "requirements": [],
            "untrusted_candidate_data": {
                "start_marker": "<untrusted_candidate_data>",
                "confirmed_fields": [],
                "evidence": [],
                "contradictions": [],
                "end_marker": "</untrusted_candidate_data>",
            },
            "missing": ["organization_mismatch"],
        }
    application, _, _, _ = resolved
    job_data = load_job_requirements(db, organization_id, application_id)
    profile = load_candidate_profile(db, organization_id, application_id)
    missing = [
        *cast(list[str], job_data["missing"]),
        *cast(list[str], profile["missing"]),
    ]
    return {
        "organization_id": str(organization_id),
        "application_id": str(application_id),
        "candidate_id": profile["candidate_id"],
        "job_id": job_data["job_id"],
        "job_version_id": job_data["job_version_id"],
        "requirements": job_data["requirements"],
        "untrusted_candidate_data": {
            "start_marker": "<untrusted_candidate_data>",
            "confirmed_fields": profile["fields"],
            "evidence": profile["evidence"],
            "contradictions": profile["contradictions"],
            "end_marker": "</untrusted_candidate_data>",
        },
        "missing": missing,
    }
