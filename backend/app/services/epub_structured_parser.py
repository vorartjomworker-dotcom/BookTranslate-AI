from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from app.services.document_parser import (
    NormalizedBlock,
    NormalizedChapter,
    NormalizedDocument,
    NormalizedSection,
)


def _book_title(book: epub.EpubBook, fallback: str) -> str:
    titles = book.get_metadata("DC", "title")
    if titles and titles[0] and titles[0][0]:
        return str(titles[0][0]).strip()
    return fallback


def _block_type(tag_name: str) -> str:
    return {
        "pre": "code",
        "blockquote": "blockquote",
        "li": "list_item",
    }.get(tag_name, "paragraph")


def parse_epub(path: Path) -> NormalizedDocument:
    book = epub.read_epub(str(path))
    title = _book_title(book, path.stem)
    chapters: list[NormalizedChapter] = []

    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        soup = BeautifulSoup(item.get_content(), "html.parser")
        for unwanted in soup(["script", "style", "nav"]):
            unwanted.decompose()

        elements = soup.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "blockquote", "li"]
        )
        first_heading = next(
            (element for element in elements if element.name and element.name.startswith("h")),
            None,
        )
        chapter_title = first_heading.get_text(" ", strip=True) if first_heading else None
        chapter = NormalizedChapter(title=chapter_title)
        section_stack: dict[int, int] = {}
        current_section_position: int | None = None

        for element in elements:
            text = element.get_text(" ", strip=True)
            if not text:
                continue

            tag_name = element.name or "p"
            if tag_name.startswith("h"):
                if element is first_heading:
                    continue

                level = int(tag_name[1:])
                parent_position = None
                for candidate_level in range(level - 1, 0, -1):
                    if candidate_level in section_stack:
                        parent_position = section_stack[candidate_level]
                        break

                section_position = len(chapter.sections)
                chapter.sections.append(
                    NormalizedSection(
                        position=section_position,
                        level=level,
                        title=text,
                        parent_position=parent_position,
                        metadata_json={"tag": tag_name, "item_id": item_id},
                    )
                )
                chapter.blocks.append(
                    NormalizedBlock(
                        position=len(chapter.blocks),
                        block_type="heading",
                        source_text=text,
                        section_position=section_position,
                        metadata_json={"level": level, "tag": tag_name},
                    )
                )
                section_stack = {key: value for key, value in section_stack.items() if key < level}
                section_stack[level] = section_position
                current_section_position = section_position
                continue

            chapter.paragraphs.append(text)
            chapter.blocks.append(
                NormalizedBlock(
                    position=len(chapter.blocks),
                    block_type=_block_type(tag_name),
                    source_text=text,
                    section_position=current_section_position,
                    metadata_json={"tag": tag_name, "item_id": item_id},
                )
            )

        if chapter.paragraphs or chapter.title or chapter.blocks:
            chapters.append(chapter)

    if not chapters:
        chapters = [NormalizedChapter(title=title)]

    return NormalizedDocument(title=title, chapters=chapters)
