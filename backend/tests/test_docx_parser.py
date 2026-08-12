from pathlib import Path

from docx import Document

from app.services.docx_parser import parse_docx


def test_docx_parser_splits_heading_one_into_chapters(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    document = Document()
    document.core_properties.title = "Sample Book"
    document.add_heading("Chapter One", level=1)
    document.add_paragraph("First paragraph.")
    document.add_heading("Chapter Two", level=1)
    document.add_paragraph("Second paragraph.")
    document.save(path)

    parsed = parse_docx(path)

    assert parsed.title == "Sample Book"
    assert [chapter.title for chapter in parsed.chapters] == ["Chapter One", "Chapter Two"]
    assert parsed.chapters[0].paragraphs == ["First paragraph."]
    assert parsed.chapters[1].paragraphs == ["Second paragraph."]
