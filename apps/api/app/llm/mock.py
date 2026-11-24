from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel

from app.agents.extraction_schema import FieldName, FieldStatus
from app.llm.provider import LLMProvider

# El CV se lee solo como dato: frases que intentan cambiar instrucciones se reportan.
_INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignora instrucciones anteriores",
    "ignora las instrucciones anteriores",
    "system prompt",
    "you are now",
)
_INJECTION_PATTERNS = tuple(
    re.compile(re.escape(phrase), re.IGNORECASE) for phrase in _INJECTION_PHRASES
)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_LABELS: dict[FieldName, tuple[str, ...]] = {
    FieldName.NAME: ("name", "nombre", "nombre completo"),
    FieldName.EMAIL: ("email", "e mail", "correo", "correo electronico"),
    FieldName.LOCATION: ("location", "ubicacion", "ubicación"),
    FieldName.EXPERIENCE: ("experience", "experiencia"),
    FieldName.EDUCATION: ("education", "educacion", "educación", "formacion"),
    FieldName.SKILLS: ("skills", "habilidades", "competencias"),
    FieldName.PROJECTS: ("projects", "proyectos"),
    FieldName.LANGUAGES: ("languages", "idiomas"),
}
_MULTI_VALUE_FIELDS = frozenset(
    {
        FieldName.SKILLS,
        FieldName.PROJECTS,
        FieldName.LANGUAGES,
    }
)
_SPLIT_VALUES = re.compile(r"\s*(?:,|;|\||·)\s*")


def _pages(context: Mapping[str, object]) -> list[tuple[int, str]]:
    raw = context.get("pages")
    if not isinstance(raw, (list, tuple)):
        return []
    pages: list[tuple[int, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        page = item.get("page")
        text = item.get("text")
        if isinstance(page, int) and page > 0 and isinstance(text, str) and text.strip():
            pages.append((page, text))
    return pages


def _quote(text: str) -> str:
    return text.strip()[:300]


def _evidence_ref(
    document_id: str, page: int, page_text: str, quote: str
) -> dict[str, object]:
    ref: dict[str, object] = {
        "document_id": document_id,
        "page": page,
        "quote": quote,
    }
    offset = page_text.find(quote)
    if offset >= 0:
        ref["offset"] = offset
    return ref


def _labeled_values(
    lines: list[str], field: FieldName, *, multi: bool
) -> list[tuple[str, str]]:
    aliases = _LABELS[field]
    found: list[tuple[str, str]] = []
    for line in lines:
        cleaned = line.strip().lstrip("•-* ").strip()
        label, separator, raw_value = cleaned.partition(":")
        if not separator or label.strip().lower() not in aliases:
            continue
        raw_value = raw_value.strip()
        if not raw_value:
            continue
        values = [part.strip() for part in _SPLIT_VALUES.split(raw_value)] if multi else [raw_value]
        values = [value for value in values if value]
        if values:
            found.append((" | ".join(values) if multi else values[0], _quote(line)))
    return found


def _empty_payload(field: FieldName) -> dict[str, object]:
    return {
        "field_name": field.value,
        "value": None,
        "status": FieldStatus.MISSING.value,
        "evidence_refs": [],
    }


def _found_payload(
    document_id: str,
    field: FieldName,
    page: int,
    page_text: str,
    value: str,
    quote: str,
    *,
    multi: bool,
) -> dict[str, object]:
    parsed_value: str | list[str]
    if multi:
        parsed_value = [part.strip() for part in value.split(" | ") if part.strip()]
    else:
        parsed_value = value
    return {
        "field_name": field.value,
        "value": parsed_value,
        "status": FieldStatus.EXTRACTED.value,
        "evidence_refs": [_evidence_ref(document_id, page, page_text, quote)],
    }


def _injection_signal(
    document_id: str, pages: list[tuple[int, str]]
) -> tuple[bool, list[dict[str, object]], set[int]]:
    refs: list[dict[str, object]] = []
    matched_pages: set[int] = set()
    for page, text in pages:
        for pattern in _INJECTION_PATTERNS:
            for match in pattern.finditer(text):
                quote = match.group(0)
                matched_pages.add(page)
                if len(refs) < 10:
                    refs.append(_evidence_ref(document_id, page, text, quote))
    return bool(matched_pages), refs, matched_pages


class MockLLMProvider(LLMProvider):
    """Proveedor determinista: solo patrones sobre el texto, sin red ni inventos."""

    def generate_structured_output(
        self,
        prompt_version: str,
        schema: type[BaseModel],
        context: Mapping[str, object],
    ) -> dict[str, object]:
        del schema  # El contrato se valida en el orquestador con `ExtractedProfile`.
        pages = _pages(context)
        document_id = str(context.get("document_id") or "")
        payloads = {field: _empty_payload(field) for field in FieldName}
        found_pages: dict[FieldName, set[int]] = {field: set() for field in FieldName}

        for page, text in pages:
            lines = text.splitlines()
            for field in FieldName:
                multi = field in _MULTI_VALUE_FIELDS
                for value, quote in _labeled_values(lines, field, multi=multi):
                    payloads[field] = _found_payload(
                        document_id, field, page, text, value, quote, multi=multi
                    )
                    found_pages[field].add(page)
            if not found_pages[FieldName.EMAIL]:
                match = _EMAIL_PATTERN.search(text)
                if match is not None:
                    quote = match.group(0)
                    payloads[FieldName.EMAIL] = _found_payload(
                        document_id,
                        FieldName.EMAIL,
                        page,
                        text,
                        quote,
                        quote,
                        multi=False,
                    )
                    found_pages[FieldName.EMAIL].add(page)

        injection_detected, injection_refs, injection_pages = _injection_signal(
            document_id, pages
        )
        for field in FieldName:
            if payloads[field]["status"] != FieldStatus.EXTRACTED.value:
                continue
            if found_pages[field] & injection_pages:
                payloads[field]["status"] = FieldStatus.NEEDS_REVIEW.value

        limitations: list[str] = ["extracted_with_simple_patterns"]
        if injection_detected:
            limitations.append("prompt_injection_detected")
        review_required = injection_detected or any(
            payload["status"] != FieldStatus.EXTRACTED.value for payload in payloads.values()
        )
        result: dict[str, object] = {
            "prompt_version": prompt_version,
            "fields": list(payloads.values()),
            "limitations": limitations,
            "review_required": review_required,
            "prompt_injection_detected": injection_detected,
            "prompt_injection_evidence": injection_refs,
        }
        return result

    def generate_text(self, prompt_version: str, context: Mapping[str, object]) -> str:
        del prompt_version
        return f"mock document text over {len(_pages(context))} pages"

    def health_check(self) -> bool:
        return True

    def estimate_usage(
        self, prompt_version: str, context: Mapping[str, object]
    ) -> dict[str, int]:
        del prompt_version
        chars = sum(len(text) for _, text in _pages(context))
        return {"prompt_tokens": max(1, chars // 4), "completion_tokens": 0}
