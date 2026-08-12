import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.block import Block
from app.models.book import Book
from app.models.caption import Caption
from app.models.chapter import Chapter
from app.models.document_table import DocumentTable
from app.models.figure import Figure
from app.models.section import Section
from app.models.segment import Segment
from app.services.document_parser import (
    NormalizedAsset,
    NormalizedBlock,
    NormalizedChapter,
    NormalizedDocument,
    NormalizedSection,
)


def _translated_text(segments: list[Segment], block_type: str) -> str | None:
    if not segments:
        return None
    values = [segment.translated_text or segment.source_text for segment in segments]
    separator = "\n" if block_type == "code" else " "
    return separator.join(value for value in values if value).strip() or None


async def load_normalized_document(
    db: AsyncSession,
    book_id: uuid.UUID,
    upload_root: Path,
    *,
    translated: bool = False,
) -> NormalizedDocument | None:
    book = await db.get(Book, book_id)
    if book is None:
        return None

    asset_rows = list(
        (await db.execute(select(Asset).where(Asset.book_id == book_id).order_by(Asset.position))).scalars().all()
    )
    normalized_assets: list[NormalizedAsset] = []
    asset_position_by_id: dict[uuid.UUID, int] = {}
    for asset in asset_rows:
        path = upload_root / asset.stored_filename
        normalized_assets.append(
            NormalizedAsset(
                position=asset.position,
                asset_type=asset.asset_type,
                original_filename=asset.original_filename,
                media_type=asset.media_type,
                data=path.read_bytes() if path.exists() else b"",
                sha256=asset.sha256,
                metadata_json=dict(asset.metadata_json or {}),
            )
        )
        asset_position_by_id[asset.id] = asset.position

    chapter_rows = list(
        (await db.execute(select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position))).scalars().all()
    )
    normalized_chapters: list[NormalizedChapter] = []

    for chapter in chapter_rows:
        segment_rows = list(
            (await db.execute(select(Segment).where(Segment.chapter_id == chapter.id).order_by(Segment.position))).scalars().all()
        )
        block_segments: dict[uuid.UUID, list[Segment]] = {}
        translated_chapter_title: str | None = None
        translated_section_titles: dict[str, str] = {}
        for segment in segment_rows:
            metadata = dict(segment.metadata_json or {})
            structural_kind = metadata.get("structural_kind")
            if translated and structural_kind == "chapter_title" and segment.translated_text:
                translated_chapter_title = segment.translated_text
            elif translated and structural_kind == "section_title" and segment.translated_text and metadata.get("section_id"):
                translated_section_titles[str(metadata["section_id"])] = segment.translated_text
            if segment.block_id is not None:
                block_segments.setdefault(segment.block_id, []).append(segment)

        section_rows = list(
            (await db.execute(select(Section).where(Section.chapter_id == chapter.id).order_by(Section.position))).scalars().all()
        )
        section_position_by_id = {section.id: section.position for section in section_rows}
        normalized_sections = [
            NormalizedSection(
                position=section.position,
                level=section.level,
                title=translated_section_titles.get(str(section.id), section.title) if translated else section.title,
                parent_position=section_position_by_id.get(section.parent_section_id) if section.parent_section_id is not None else None,
                metadata_json=dict(section.metadata_json or {}),
            )
            for section in section_rows
        ]

        block_rows = list(
            (await db.execute(select(Block).where(Block.chapter_id == chapter.id).order_by(Block.position))).scalars().all()
        )
        block_ids = [block.id for block in block_rows]
        block_position_by_id = {block.id: block.position for block in block_rows}

        tables_by_block = {}
        figures_by_block = {}
        captions_by_block = {}
        if block_ids:
            tables_by_block = {
                row.block_id: row
                for row in (await db.execute(select(DocumentTable).where(DocumentTable.block_id.in_(block_ids)))).scalars().all()
            }
            figures_by_block = {
                row.block_id: row
                for row in (await db.execute(select(Figure).where(Figure.block_id.in_(block_ids)))).scalars().all()
            }
            captions_by_block = {
                row.block_id: row
                for row in (await db.execute(select(Caption).where(Caption.block_id.in_(block_ids)))).scalars().all()
            }

        normalized_blocks: list[NormalizedBlock] = []
        paragraphs: list[str] = []
        for block in block_rows:
            metadata = dict(block.metadata_json or {})
            table = tables_by_block.get(block.id)
            if table is not None:
                metadata["cells"] = list((table.data_json or {}).get("cells", []))
                metadata["rows_count"] = table.rows_count
                metadata["columns_count"] = table.columns_count

            figure = figures_by_block.get(block.id)
            if figure is not None:
                metadata["asset_position"] = asset_position_by_id.get(figure.asset_id)
                metadata["alt_text"] = figure.alt_text

            caption = captions_by_block.get(block.id)
            if caption is not None:
                metadata["target_block_position"] = block_position_by_id.get(caption.target_block_id) if caption.target_block_id is not None else None
                metadata["label"] = caption.label

            text = block.source_text
            if translated:
                if block.block_type == "heading" and block.section_id is not None:
                    text = translated_section_titles.get(str(block.section_id), text)
                elif block.block_type not in {"figure", "table"}:
                    text = _translated_text(block_segments.get(block.id, []), block.block_type) or text

            normalized_blocks.append(
                NormalizedBlock(
                    position=block.position,
                    block_type=block.block_type,
                    source_text=text,
                    section_position=section_position_by_id.get(block.section_id) if block.section_id is not None else None,
                    metadata_json=metadata,
                )
            )
            if text and block.block_type not in {"heading", "table", "figure"}:
                paragraphs.append(text)

        normalized_chapters.append(
            NormalizedChapter(
                title=translated_chapter_title or chapter.title if translated else chapter.title,
                paragraphs=paragraphs,
                sections=normalized_sections,
                blocks=normalized_blocks,
            )
        )

    return NormalizedDocument(title=book.title, chapters=normalized_chapters, assets=normalized_assets)
