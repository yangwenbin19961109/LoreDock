from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from loredock.ingestion import parse_path


def test_text_parser_rejects_path_outside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        parse_path(outside, allowed_root=allowed)


def test_docx_parser_preserves_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("第一段")
    document.add_paragraph("Second paragraph")
    document.save(str(path))

    parsed = parse_path(path)

    assert parsed.text == "第一段\n\nSecond paragraph"


def test_pdf_parser_records_page_spans(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as output:
        writer.write(output)

    parsed = parse_path(path)

    assert parsed.page_spans == ((1, 0, 0),)
