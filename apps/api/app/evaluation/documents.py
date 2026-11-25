from __future__ import annotations

import io

from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.evaluation.dataset import CvFormat, DatasetCase


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )

    operations = ["BT", "/F1 12 Tf", "72 720 Td"]
    for line in text.splitlines():
        operations.append(f"({_escape_pdf_text(line)}) Tj")
        operations.append("0 -16 Td")
    operations.append("ET")

    stream = DecodedStreamObject()
    stream.set_data("\n".join(operations).encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def render_docx(text: str) -> bytes:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def render_case(case: DatasetCase) -> bytes:
    if case.format is CvFormat.PDF:
        return render_pdf(case.text)
    return render_docx(case.text)
