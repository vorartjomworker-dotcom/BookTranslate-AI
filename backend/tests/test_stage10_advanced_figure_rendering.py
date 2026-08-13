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
from app.services.figure_rendering import render_asset
from app.storage.local import LocalStorage

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


def _source_png() -> bytes:
    image = Image.new("RGB", (320, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.line((0, 80, 320, 80), fill=(80, 130, 180), width=5)
    draw.text((95, 55), "CPU", fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def _run(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    source = _source_png()
    source_key = "assets/stage10/source.png"
    await storage.put_bytes(source_key, source, content_type="image/png")

    async with AsyncSessionLocal() as db:
        book = Book(title="Stage 10 Figure", source_language="en", target_language="ru", status="translated")
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
        db.add(Figure(block_id=block.id, asset_id=asset.id, alt_text="CPU diagram", metadata_json={}))
        db.add(
            Segment(
                chapter_id=chapter.id,
                block_id=block.id,
                position=0,
                segment_type="figure_text",
                source_text="CPU",
                translated_text="Процессор",
                source_hash=hashlib.sha256(b"CPU").hexdigest(),
                status="translated",
                metadata_json={"asset_id": str(asset.id), "bbox": [0.26, 0.26, 0.73, 0.68], "kind": "label"},
            )
        )
        await db.commit()

        inpaint = await render_asset(db, storage, asset=asset, target_language="ru", render_mode="inpaint")
        await db.commit()
        assert inpaint.render_mode == "inpaint"
        assert inpaint.metadata_json["renderer"] == "opencv-telea-inpaint-v1"
        inpaint_png = await storage.get_bytes(inpaint.stored_filename)
        assert inpaint_png.startswith(b"\x89PNG")
        assert inpaint_png != source

        vector = await render_asset(db, storage, asset=asset, target_language="ru", render_mode="vector")
        await db.commit()
        assert vector.render_mode == "vector"
        svg_key = vector.metadata_json.get("vector_svg_key")
        assert svg_key
        svg = await storage.get_bytes(svg_key)
        assert svg.startswith(b"<svg")
        assert "Процессор" in svg.decode("utf-8")
        assert b"data:image/png;base64" in svg

        vector_again = await render_asset(db, storage, asset=asset, target_language="ru", render_mode="vector")
        assert vector_again.id == vector.id

        await db.delete(book)
        await db.commit()
    await engine.dispose()


def test_inpaint_and_vector_render_modes(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path))
