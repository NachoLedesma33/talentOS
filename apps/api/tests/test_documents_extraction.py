from __future__ import annotations

import io
import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.documents import storage as storage_module
from app.documents.extraction import ExtractionError, extract_text
from app.documents.validation import MAX_PAGES

_CORRUPT_MARKER = "SyntheticCVSecret"


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "var" / "documents"
    monkeypatch.setattr(storage_module, "_base_dir", lambda: root)
    return root


def _pdf_bytes(texts: list[str]) -> bytes:
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=200, height=200)
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 20 180 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _docx_bytes(tmp_path: Path, paragraphs: list[str]) -> bytes:
    document = DocxDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    path = tmp_path / "synthetic.docx"
    document.save(path)
    return path.read_bytes()


def _store(
    root: Path,
    *,
    organization_id: UUID,
    document_id: UUID,
    internal_name: str,
    data: bytes,
) -> None:
    storage_module.store_document(
        organization_id=organization_id,
        document_id=document_id,
        internal_name=internal_name,
        data=data,
    )


def test_pdf_extraction_preserves_page_numbers_text_and_offsets(storage_root: Path) -> None:
    organization_id, document_id = uuid4(), uuid4()
    _store(
        storage_root,
        organization_id=organization_id,
        document_id=document_id,
        internal_name="synthetic.pdf",
        data=_pdf_bytes(["Synthetic alpha", "Synthetic beta"]),
    )

    pages = extract_text(
        document_id=document_id,
        internal_name="synthetic.pdf",
        extension=".pdf",
        organization_id=organization_id,
    )

    assert [page["page"] for page in pages] == [1, 2]
    assert "Synthetic alpha" in str(pages[0]["text"])
    assert "Synthetic beta" in str(pages[1]["text"])
    assert pages[0]["start_offset"] == 0
    assert pages[0]["end_offset"] == pages[1]["start_offset"]
    assert pages[1]["end_offset"] == sum(len(str(page["text"])) for page in pages)


def test_docx_extraction_joins_paragraphs_into_one_logical_page(
    storage_root: Path, tmp_path: Path
) -> None:
    organization_id, document_id = uuid4(), uuid4()
    _store(
        storage_root,
        organization_id=organization_id,
        document_id=document_id,
        internal_name="synthetic.docx",
        data=_docx_bytes(tmp_path, ["Synthetic one", "Synthetic two"]),
    )

    pages = extract_text(
        document_id=document_id,
        internal_name="synthetic.docx",
        extension=".docx",
        organization_id=organization_id,
    )

    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert "Synthetic one\nSynthetic two" in str(pages[0]["text"])


def test_empty_pdf_and_docx_report_empty_document(storage_root: Path, tmp_path: Path) -> None:
    cases = (
        ("synthetic.pdf", ".pdf", b""),
        ("synthetic.docx", ".docx", _docx_bytes(tmp_path, [])),
    )
    for internal_name, extension, data in cases:
        organization_id, document_id = uuid4(), uuid4()
        _store(
            storage_root,
            organization_id=organization_id,
            document_id=document_id,
            internal_name=internal_name,
            data=data,
        )
        with pytest.raises(ExtractionError) as exc:
            extract_text(
                document_id=document_id,
                internal_name=internal_name,
                extension=extension,
                organization_id=organization_id,
            )
        assert exc.value.code == "empty_document"
        assert str(exc.value) == "empty_document"


def test_corrupt_pdf_and_docx_report_corrupt_document(storage_root: Path) -> None:
    cases = (
        ("synthetic.pdf", ".pdf", b"%PDF-1.4\nSyntheticCVSecret\n"),
        ("synthetic.docx", ".docx", b"PK\x03\x04SyntheticCVSecret"),
    )
    for internal_name, extension, data in cases:
        organization_id, document_id = uuid4(), uuid4()
        _store(
            storage_root,
            organization_id=organization_id,
            document_id=document_id,
            internal_name=internal_name,
            data=data,
        )
        with pytest.raises(ExtractionError) as exc:
            extract_text(
                document_id=document_id,
                internal_name=internal_name,
                extension=extension,
                organization_id=organization_id,
            )
        assert exc.value.code == "corrupt_document"
        assert _CORRUPT_MARKER not in str(exc.value)


def test_pdf_above_page_limit_reports_too_many_pages(storage_root: Path) -> None:
    organization_id, document_id = uuid4(), uuid4()
    _store(
        storage_root,
        organization_id=organization_id,
        document_id=document_id,
        internal_name="synthetic.pdf",
        data=_pdf_bytes([f"Synthetic page {number}" for number in range(MAX_PAGES + 1)]),
    )

    with pytest.raises(ExtractionError) as exc:
        extract_text(
            document_id=document_id,
            internal_name="synthetic.pdf",
            extension=".pdf",
            organization_id=organization_id,
        )

    assert exc.value.code == "too_many_pages"


def test_extraction_does_not_print_or_log_document_text(
    storage_root: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    organization_id, document_id = uuid4(), uuid4()
    _store(
        storage_root,
        organization_id=organization_id,
        document_id=document_id,
        internal_name="synthetic.pdf",
        data=_pdf_bytes(["SyntheticCVSecret"]),
    )
    caplog.set_level(logging.DEBUG)

    pages = extract_text(
        document_id=document_id,
        internal_name="synthetic.pdf",
        extension=".pdf",
        organization_id=organization_id,
    )

    assert "SyntheticCVSecret" in str(pages[0]["text"])
    assert capsys.readouterr().out == ""
    assert _CORRUPT_MARKER not in caplog.text
