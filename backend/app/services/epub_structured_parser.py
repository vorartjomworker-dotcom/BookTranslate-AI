import hashlib
import posixpath
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from app.services.document_parser import (
    NormalizedAsset,
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
    return {"pre": "code", "blockquote": "blockquote", "li": "list_item"}.get(tag_name, "paragraph")


def _find_item(book: epub.EpubBook, current_name: str, href: str):
    href = href.split("#", 1)[0]
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(current_name), href))
    for candidate in (resolved, href):
        item = book.get_item_with_href(candidate)
        if item is not None:
            return item
    return None


def _register_asset(
    assets: list[NormalizedAsset],
    by_hash: dict[str, int],
    data: bytes,
    filename: str | None,
    media_type: str | None,
    metadata_json: dict,
) -> int:
    digest = hashlib.sha256(data).hexdigest()
    existing = by_hash.get(digest)
    if existing is not None:
        return existing
    position = len(assets)
    assets.append(
        NormalizedAsset(
            position=position,
            original_filename=filename,
            media_type=media_type,
            data=data,
            sha256=digest,
            metadata_json=metadata_json,
        )
    )
    by_hash[digest] = position
    return position


def parse_epub(path: Path) -> NormalizedDocument:
    book = epub.read_epub(str(path))
    title = _book_title(book, path.stem)
    chapters: list[NormalizedChapter] = []
    assets: list[NormalizedAsset] = []
    assets_by_hash: dict[str, int] = {}

    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        soup = BeautifulSoup(item.get_content(), "html.parser")
        for unwanted in soup(["script", "style", "nav"]):
            unwanted.decompose()

        elements = soup.find_all(
            [
                "h1", "h2", "h3", "h4", "h5", "h6",
                "p", "pre", "blockquote", "li", "img", "table", "figcaption", "caption",
            ]
        )
        first_heading = next(
            (element for element in elements if element.name and element.name.startswith("h")),
            None,
        )
        chapter_title = first_heading.get_text(" ", strip=True) if first_heading else None
        chapter = NormalizedChapter(title=chapter_title)
        section_stack: dict[int, int] = {}
        current_section_position: int | None = None
        last_target_block_position: int | None = None

        for element in elements:
            tag_name = element.name or "p"
            if tag_name in {"p", "pre", "blockquote", "li", "img"} and element.find_parent("table"):
                continue
            if tag_name == "p" and element.find_parent(["li", "figcaption"]):
                continue

            if tag_name.startswith("h"):
                text = element.get_text(" ", strip=True)
                if not text or element is first_heading:
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

            if tag_name == "img":
                href = element.get("src")
                if not href:
                    continue
                asset_item = _find_item(book, item.get_name(), href)
                if asset_item is None:
                    continue
                data = asset_item.get_content()
                asset_position = _register_asset(
                    assets,
                    assets_by_hash,
                    data,
                    Path(asset_item.get_name()).name,
                    getattr(asset_item, "media_type", None),
                    {"source": "epub", "href": href, "item_id": item_id},
                )
                block_position = len(chapter.blocks)
                chapter.blocks.append(
                    NormalizedBlock(
                        position=block_position,
                        block_type="figure",
                        section_position=current_section_position,
                        metadata_json={
                            "asset_position": asset_position,
                            "alt_text": element.get("alt"),
                            "source_href": href,
                        },
                    )
                )
                last_target_block_position = block_position
                continue

            if tag_name == "table":
                cells = [
                    [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
                    for row in element.find_all("tr")
                ]
                cells = [row for row in cells if row]
                source_text = "\n".join("\t".join(row) for row in cells)
                block_position = len(chapter.blocks)
                chapter.blocks.append(
                    NormalizedBlock(
                        position=block_position,
                        block_type="table",
                        source_text=source_text,
                        section_position=current_section_position,
                        metadata_json={
                            "cells": cells,
                            "rows_count": len(cells),
                            "columns_count": max((len(row) for row in cells), default=0),
                            "tag": "table",
                        },
                    )
                )
                last_target_block_position = block_position
                continue

            text = element.get_text(" ", strip=True)
            if not text:
                continue
            if tag_name in {"figcaption", "caption"}:
                chapter.paragraphs.append(text)
                chapter.blocks.append(
                    NormalizedBlock(
                        position=len(chapter.blocks),
                        block_type="caption",
                        source_text=text,
                        section_position=current_section_position,
                        metadata_json={
                            "tag": tag_name,
                            "target_block_position": last_target_block_position,
                        },
                    )
                )
                continue

            chapter.paragraphs.append(text)
            metadata = {"tag": tag_name, "item_id": item_id}
            if tag_name == "li":
                parent = element.find_parent(["ol", "ul"])
                metadata["list_kind"] = "number" if parent and parent.name == "ol" else "bullet"
            chapter.blocks.append(
                NormalizedBlock(
                    position=len(chapter.blocks),
                    block_type=_block_type(tag_name),
                    source_text=text,
                    section_position=current_section_position,
                    metadata_json=metadata,
                )
            )

        if chapter.paragraphs or chapter.title or chapter.blocks:
            chapters.append(chapter)

    if not chapters:
        chapters = [NormalizedChapter(title=title)]

    return NormalizedDocument(title=title, chapters=chapters, assets=assets)
