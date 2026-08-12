import re
from pathlib import Path

from docx import Document

from app.services.document_parser import (
    NormalizedBlock,
    NormalizedChapter,
    NormalizedDocument,
    NormalizedSection,
)


_HEADING_LEVEL = re.compile(r"(?:heading|заголовок)\s*(\d+)", re.IGNORECASE)


def _heading_level(style_name: str) -> int | None:
    match = _HEADING_LEVEL.search(style_name)
    return int(match.group(1)) if match else None


def _block_type(style_name: str) -> str:
    lowered = style_name.lower()
    if "list" in lowered or "спис" in lowered:
        return "list_item"
    if "code" in lowered or "preformatted" in lowered or "код" in lowered:
        return "code"
    if "quote" in lowered or "цитат" in lowered:
        return "blockquote"
    return "paragraph"


def _append_text_block(chapter: NormalizedChapter, text: str, style_name: str, section_position: int | None) -> None:
    block_type = _block_type(style_name)
    chapter.paragraphs.append(text)
    chapter.blocks.append(
        NormalizedBlock(
            position=len(chapter.blocks),
            block_type=block_type,
            source_text=text,
            section_position=section_position,
            metadata_json={"style": style_name},
        )
    )


def parse_docx(path: Path) -> NormalizedDocument:
    document = Document(path)
    title = (document.core_properties.title or "").strip() or path.stem

    chapters: list[NormalizedChapter] = []
    current = NormalizedChapter(title=None)
    section_stack: dict[int, int] = {}
    current_section_position: int | None = None

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = (paragraph.style.name or "") if paragraph.style else ""
        heading_level = _heading_level(style_name)

        if heading_level == 1:
            if current.paragraphs or current.title or current.blocks:
                chapters.append(current)
            current = NormalizedChapter(title=text)
            section_stack = {}
            current_section_position = None
            continue

        if heading_level and heading_level >= 2:
            parent_position = None
            for candidate_level in range(heading_level - 1, 1, -1):
                if candidate_level in section_stack:
                    parent_position = section_stack[candidate_level]
                    break

            section_position = len(current.sections)
            current.sections.append(
                NormalizedSection(
                    position=section_position,
                    level=heading_level,
                    title=text,
                    parent_position=parent_position,
                    metadata_json={"style": style_name},
                )
            )
            current.blocks.append(
                NormalizedBlock(
                    position=len(current.blocks),
                    block_type="heading",
                    source_text=text,
                    section_position=section_position,
                    metadata_json={"level": heading_level, "style": style_name},
                )
            )
            section_stack = {level: pos for level, pos in section_stack.items() if level < heading_level}
            section_stack[heading_level] = section_position
            current_section_position = section_position
            continue

        _append_text_block(current, text, style_name, current_section_position)

    if current.paragraphs or current.title or current.blocks:
        chapters.append(current)

    if not chapters:
        chapters = [NormalizedChapter(title=title)]
    elif len(chapters) == 1 and chapters[0].title is None:
        chapters[0].title = title

    return NormalizedDocument(title=title, chapters=chapters)
