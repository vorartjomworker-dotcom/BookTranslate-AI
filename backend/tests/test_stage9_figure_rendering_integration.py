import asyncio
import hashlib
import io
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.db import AsyncSessionLocal, engine
from app.models.asset import Asset
from app.models.block import Block
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.figure import Figure
from app.models.segment import Segment
from app.services.document_export import load_normalized_document
from app.services.figure_rendering import render_asset
from app.storage.local import LocalStorage

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


def _source_png() -> bytes:
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.text((45, 55), "Latency", fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def _run(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    source = _source_png()
    source_key = "assets/stage9/source.png"
    await storage.put_bytes(source_key, source, content_type="image/png")

    async with AsyncSessionLocal() as db:
        book = Book(title="Stage 9 Figure", source_language="en", target_language="ru", status="translated")
        db.add(book)
        await db.flush()
        chapter = Chapter(book_id=book.id, position=0, title="Chapter", source_text="")
        db.add(chapter)
        await db.flush()
        block = Block(chapter_id=chapter.id, position=0, block_type="figure", source_text=None, metadata_json={})
        db.add(block)
        asset = Asset(
            book_id=book.id,
            position=0,
            asset_type="image",
            original_filename="source.png",
            stored_filename=source_key,
            media_type="image/png",
            sha256=hashlib.sha256(source).hexdigest(),
            metadata_json={},
        )
        db.add(asset)
        await db.flush()
        db.add(Figure(block_id=block.id, asset_id=asset.id, alt_text="latency chart", metadata_json={}))
        segment = Segment(
            chapter_id=chapter.id,
            block_id=block.id,
            position=0,
            segment_type="figure_text",
            source_text="Latency",
            translated_text="Translated latency",
            source_hash=hashlib.sha256(b"Latency").hexdigest(),
            status="translated",
            metadata_json={"asset_id": str(asset.id), "bbox": [0.08, 0.20, 0.60, 0.55], "kind": "label"},
        )
        db.add(segment)
        await db.commit()

        render = await render_asset(db, storage, asset=asset, target_language="ru")
        await db.commit()
        assert render.status == "completed"
        assert render.rendered_regions == 1
        assert render.total_regions == 1
        rendered_bytes = await storage.get_bytes(render.stored_filename)
        assert rendered_bytes.startswith(b"\x89PNG")
        assert hashlib.sha256(rendered_bytes).hexdigest() == render.sha256
        assert rendered_bytes != source

        document = await load_normalized_document(db, book.id, tmp_path, translated=True, storage=storage)
        assert document is not None
        assert document.assets[0].data == rendered_bytes
        assert document.assets[0].metadata_json["translated_figure_render"] is True

        same = await render_asset(db, storage, asset=asset, target_language="ru")
        assert same.id == render.id

        await db.delete(book)
        await db.commit()
    await engine.dispose()


def test_figure_render_becomes_translated_export_asset(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path))
