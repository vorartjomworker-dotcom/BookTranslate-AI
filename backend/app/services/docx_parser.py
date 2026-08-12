from pathlib import Path

from docx import Document

from app.services.document_parser import NormalizedChapter, NormalizedDocument


def parse_docx(path: Path) -> NormalizedDocument:
    document = Document(path)
    title = (document.core_properties.title or "").strip() or path.stem

    chapters: list[NormalizedChapter] = []
    current = NormalizedChapter(title=None)

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
        is_heading_one = style_name.startswith("heading 1") or style_name.startswith("заголовок 1")

        if is_heading_one:
            if current.paragraphs or current.title:
                chapters.append(current)
            current = NormalizedChapter(title=text)
            continue

        current.paragraphs.append(text)

    if current.paragraphs or current.title:
        chapters.append(current)

    if not chapters:
        chapters = [NormalizedChapter(title=title, paragraphs=[])]
    elif len(chapters) == 1 and chapters[0].title is None:
        chapters[0].title = title

    return NormalizedDocument(title=title, chapters=chapters)
