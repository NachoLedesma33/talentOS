from __future__ import annotations

import io
import re

import pytest
from docx import Document as DocxDocument
from pydantic import ValidationError
from pypdf import PdfReader

from app.agents.extraction_schema import FieldName, FieldStatus
from app.evaluation.dataset import (
    DATASET_CASES,
    DATASET_VERSION,
    CvFormat,
    DatasetCase,
    ExpectedField,
)
from app.evaluation.documents import render_case

_REQUIRED_FLAGS = {
    "complete",
    "incomplete",
    "ambiguous",
    "missing_requirement",
    "contradiction",
    "prompt_injection",
    "malformed",
}


def test_dataset_is_versioned_and_covers_required_edge_cases() -> None:
    assert DATASET_VERSION == "1.0.0"
    assert len(DATASET_CASES) == 7
    assert len({case.id for case in DATASET_CASES}) == len(DATASET_CASES)
    assert {case.format for case in DATASET_CASES} == {CvFormat.PDF, CvFormat.DOCX}

    flags = {flag for case in DATASET_CASES for flag in case.flags}
    assert _REQUIRED_FLAGS <= flags


def test_expected_evidence_is_verbatim_and_pii_is_synthetic() -> None:
    for case in DATASET_CASES:
        for field in case.expected_fields:
            for quote in field.quotes:
                assert quote in case.text
        for quote in case.expected_prompt_injection_quotes:
            assert quote in case.text
        for email in re.findall(r"[^\s]+@[^\s]+", case.text):
            assert email.endswith("@example.test")


def test_injection_case_declares_detection() -> None:
    injection_cases = [case for case in DATASET_CASES if "prompt_injection" in case.flags]
    assert len(injection_cases) == 1
    case = injection_cases[0]
    assert case.prompt_injection_detected
    assert case.expected_prompt_injection_quotes


def test_dataset_rejects_expected_quote_absent_from_cv_text() -> None:
    with pytest.raises(ValidationError):
        DatasetCase(
            id="bad-evidence",
            format=CvFormat.PDF,
            text="Name: Synthetic Halo\n",
            flags=frozenset({"malformed"}),
            expected_fields=(
                ExpectedField(
                    field_name=FieldName.NAME,
                    status=FieldStatus.EXTRACTED,
                    value="Synthetic Halo",
                    quotes=("not present",),
                ),
            ),
            review_required=True,
            prompt_injection_detected=False,
        )


def test_rendered_pdf_cases_preserve_synthetic_text() -> None:
    for case in DATASET_CASES:
        if case.format is not CvFormat.PDF:
            continue
        data = render_case(case)
        assert data.startswith(b"%PDF-")
        extracted = PdfReader(io.BytesIO(data)).pages[0].extract_text() or ""
        assert case.text.rstrip("\n") in extracted


def test_rendered_docx_cases_preserve_synthetic_text() -> None:
    for case in DATASET_CASES:
        if case.format is not CvFormat.DOCX:
            continue
        data = render_case(case)
        assert data.startswith(b"PK")
        document = DocxDocument(io.BytesIO(data))
        assert "\n".join(paragraph.text for paragraph in document.paragraphs) == case.text.rstrip(
            "\n"
        )
