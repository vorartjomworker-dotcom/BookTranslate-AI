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
from app.models.figure_render import FigureRender
from app.models.section import Section
from app.models.segment import Segment
from app.services.document_parser import NormalizedAsset, NormalizedBlock, NormalizedChapter, NormalizedDocument, NormalizedSection
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage


def _translated_text(segments: list[Segment], block_type: str) -> str | None:
    if not segments:
        return None
    values = [segment.translated_text or segment.source_text for segment in segments]
    separator = "\n" if block_type in {"code", "table"} else " "
    return separator.join(value for value in values if value).strip() or None


def _translated_table_cells(segments: list[Segment], *, rows_count: int, columns_count: int) -> list[list[str]] | None:
    if not segments or not any(segment.translated_text for segment in segments):
        return None
    text = _translated_text(segments, "table")
    if not text:
        return None
    rows = [line.split("\t") for line in text.splitlines()]
    if len(rows) != rows_count or any(len(row) != columns_count for row in rows):
        return None
    return rows


async def load_normalized_document(
    db: AsyncSession,
    book_id: uuid.UUID,
    upload_root: Path,
    *,
    translated: bool = False,
    storage: StorageBackend | None = None,
) -> NormalizedDocument | None:
    book = await db.get(Book, book_id)
    if book is None:
        return None
    storage = storage or LocalStorage(upload_root)

    render_by_asset: dict[uuid.UUID, FigureRender] = {}
    if translated:
        render_rows = list(
            (
                await db.execute(
                    select(FigureRender)
                    .where(
                        FigureRender.book_id == book_id,
                        FigureRender.target_language == book.target_language,
                        FigureRender.status == "completed",
                    )
                    .order_by(FigureRender.created_at.desc())
                )
            ).scalars().all()
        )
        for render in render_rows:
            render_by_asset.setdefault(render.asset_id, render)

    asset_rows = list((await db.execute(select(Asset).where(Asset.book_id == book_id).order_by(Asset.position))).scalars().all())
    normalized_assets: list[NormalizedAsset] = []
    asset_position_by_id: dict[uuid.UUID, int] = {}
    for asset in asset_rows:
        render = render_by_asset.get(asset.id)
        key = render.stored_filename if render is not None else asset.stored_filename
        try:
            data = await storage.get_bytes(key)
        except FileNotFoundError:
            data = b""
        metadata = dict(asset.metadata_json or {})
        if render is not None:
            metadata.update({"translated_figure_render": True, "figure_render_id": str(render.id), "source_asset_sha256": asset.sha256})
        normalized_assets.append(
            NormalizedAsset(
                position=asset.position,
                asset_type=asset.asset_type,
                original_filename=asset.original_filename,
                media_type=render.media_type if render is not None else asset.media_type,
                data=data,
                sha256=render.sha256 if render is not None else asset.sha256,
                metadata_json=metadata,
            )
        )
        asset_position_by_id[asset.id] = asset.position

    chapter_rows = list((await db.execute(select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position))).scalars().all())
    normalized_chapters: list[NormalizedChapter] = []
    for chapter in chapter_rows:
        segment_rows = list((await db.execute(select(Segment).where(Segment.chapter_id == chapter.id).order_by(Segment.position))).scalars().all())
        block_segments: dict[uuid.UUID, list[Segment]] = {}
        translated_chapter_title: str | None = None
        translated_section_titles: dict[str, str] = {}
        for segment in segment_rows:
            segment_metadata = dict(segment.metadata_json or {})
            structural_kind = segment_metadata.get("structural_kind")
            if translated and structural_kind == "chapter_title" and segment.translated_text:
                translated_chapter_title = segment.translated_text
            elif translated and structural_kind == "section_title" and segment.translated_text and segment_metadata.get("section_id"):
                translated_section_titles[str(segment_metadata["section_id"])] = segment.translated_text
            if segment.block_id is not None:
                block_segments.setdefault(segment.block_id, []).append(segment)

        section_rows = list((await db.execute(select(Section).where(Section.chapter_id == chapter.id).order_by(Section.position))).scalars().all())
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

        block_rows = list((await db.execute(select(Block).where(Block.chapter_id == chapter.id).order_by(Block.position))).scalars().all())
        block_ids = [block.id for block in block_rows]
        block_position_by_id = {block.id: block.position for block in block_rows}
        tables_by_block = {}
        figures_by_block = {}
        captions_by_block = {}
        if block_ids:
            tables_by_block = {row.block_id: row for row in (await db.execute(select(DocumentTable).where(DocumentTable.block_id.in_(block_ids)))).scalars().all()}
            figures_by_block = {row.block_id: row for row in (await db.execute(select(Figure).where(Figure.block_id.in_(block_ids)))).scalars().all()}
            captions_by_block = {row.block_id: row for row in (await db.execute(select(Caption).where(Caption.block_id.in_(block_ids)))).scalars().all()}

        normalized_blocks: list[NormalizedBlock] = []
        paragraphs: list[str] = []
        for block in block_rows:
            metadata = dict(block.metadata_json or {})
            table = tables_by_block.get(block.id)
            if table is not None:
                source_cells = list((table.data_json or {}).get("cells", []))
                metadata["cells"] = source_cells
                metadata["rows_count"] = table.rows_count
                metadata["columns_count"] = table.columns_count
                if translated:
                    translated_cells = _translated_table_cells(block_segments.get(block.id, []), rows_count=table.rows_count, columns_count=table.columns_count)
                    if translated_cells is not None:
                        metadata["cells"] = translated_cells
                        metadata["translated_table"] = True

            figure = figures_by_block.get(block.id)
            if figure is not None:
                metadata["asset_position"] = asset_position_by_id.get(figure.asset_id)
                metadata["alt_text"] = figure.alt_text
                if translated and figure.asset_id in render_by_asset:
                    metadata["translated_figure_render"] = True
                    metadata["figure_render_id"] = str(render_by_asset[figure.asset_id].id)

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

            normalized_blocks.append(NormalizedBlock(position=block.position, block_type=block.block_type, source_text=text, section_position=section_position_by_id.get(block.section_id) if block.section_id is not None else None, metadata_json=metadata))
            if text and block.block_type not in {"heading", "table", "figure"}:
                paragraphs.append(text)

        chapter_title = translated_chapter_title if translated and translated_chapter_title else chapter.title
        normalized_chapters.append(NormalizedChapter(title=chapter_title, paragraphs=paragraphs, sections=normalized_sections, blocks=normalized_blocks))

    return NormalizedDocument(title=book.title, chapters=normalized_chapters, assets=normalized_assets)
