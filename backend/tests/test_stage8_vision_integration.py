import asyncio
import hashlib
import os
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal, engine
from app.models.asset import Asset
from app.models.block import Block
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.figure import Figure
from app.models.segment import Segment
from app.models.vision_extraction import VisionExtraction
from app.models.vision_job import VisionJob
from app.services.vision_jobs import process_vision_job
from app.vision.gateway import VisionGateway
from app.vision.schemas import VisionResult

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


class FakeVisionProvider:
    name = "fake"

    async def extract(self, *, image_bytes: bytes, media_type: str, model: str, prompt: str) -> VisionResult:
        assert image_bytes == b"image-bytes"
        assert media_type == "image/png"
        return VisionResult(
            text="Latency 12 us\nThroughput",
            regions=[
                {"text": "Latency 12 us", "kind": "label", "bbox": [0.1, 0.2, 0.4, 0.3]},
                {"text": "Throughput", "kind": "axis", "bbox": [0.0, 0.8, 0.2, 0.9]},
            ],
            raw={"status": "completed"},
            provider="fake",
            model=model,
            request_id="vision-1",
            input_tokens=10,
            output_tokens=8,
        )


async def _run(tmp_path: Path) -> None:
    (tmp_path / "asset.png").write_bytes(b"image-bytes")
    async with AsyncSessionLocal() as db:
        book = Book(title="Vision Book", source_language="en", target_language="ru", status="parsed")
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
            original_filename="asset.png",
            stored_filename="asset.png",
            media_type="image/png",
            sha256=hashlib.sha256(b"image-bytes").hexdigest(),
            metadata_json={},
        )
        db.add(asset)
        await db.flush()
        db.add(Figure(block_id=block.id, asset_id=asset.id, alt_text="benchmark", metadata_json={}))
        job = VisionJob(book_id=book.id, status="queued", provider="fake", model="fake-vision", prompt="extract", metadata_json={})
        db.add(job)
        await db.commit()
        await db.refresh(job)

        gateway = VisionGateway({"fake": FakeVisionProvider()})
        result = await process_vision_job(db, gateway, job.id, upload_dir=tmp_path)
        assert result.status == "completed"
        assert result.completed_assets == 1
        assert result.failed_assets == 0

        extraction = (
            await db.execute(select(VisionExtraction).where(VisionExtraction.asset_id == asset.id))
        ).scalar_one()
        assert extraction.extracted_text == "Latency 12 us\nThroughput"
        assert len(extraction.regions_json) == 2

        segments = list(
            (
                await db.execute(
                    select(Segment).where(Segment.block_id == block.id, Segment.segment_type == "figure_text").order_by(Segment.position)
                )
            ).scalars().all()
        )
        assert [segment.source_text for segment in segments] == ["Latency 12 us", "Throughput"]
        assert segments[0].metadata_json["asset_id"] == str(asset.id)
        assert segments[0].metadata_json["bbox"] == [0.1, 0.2, 0.4, 0.3]

        await db.delete(book)
        await db.commit()
    await engine.dispose()


def test_vision_job_creates_translatable_figure_segments(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path))
