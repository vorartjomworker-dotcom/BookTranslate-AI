import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.ai.gateway import ModelGateway
from app.ai.providers.base import ModelProvider
from app.ai.schemas import ModelRequest, ModelResponse
from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.models.block import Block
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.segment import Segment
from app.models.translation_job import TranslationJob
from app.models.translation_memory import TranslationMemoryEntry
from app.models.translation_qa_result import TranslationQAResult
from app.models.translation_version import TranslationVersion
from app.redis_client import redis_client
from app.services.document_export import load_normalized_document
from app.services.job_queue import dequeue_job
from app.services.translation_jobs import create_job, process_job

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL and Redis integration services",
)


class Stage4FakeProvider(ModelProvider):
    name = "fake-stage4"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        role = str(request.metadata.get("role"))
        if role == "qa_evaluator":
            text = json.dumps(
                {
                    "semantic_accuracy": 92,
                    "terminology": 88,
                    "completeness": 95,
                    "fluency": 90,
                    "technical_integrity": 94,
                    "style": 89,
                    "issues": ["minor terminology preference"],
                }
            )
        else:
            source = request.user_prompt.split("[SOURCE]\n", 1)[-1].split("\n\n", 1)[0]
            text = f"RU::{source}"
        return ModelResponse(
            text=text,
            provider=self.name,
            model=request.model,
            request_id=f"stage4-{role}",
            input_tokens=20,
            output_tokens=10,
        )


async def _run() -> None:
    gateway = ModelGateway()
    gateway.register(Stage4FakeProvider())
    queue_name = "translation-stage4-test"
    queue_key = f"booktranslate:queue:{queue_name}"
    marker_key = f"booktranslate:queued:{queue_name}"
    await redis_client.delete(queue_key, marker_key)

    try:
        async with AsyncSessionLocal() as db:
            book = Book(title="Stage 4", source_language="en", target_language="ru")
            db.add(book)
            await db.flush()
            chapter = Chapter(book_id=book.id, position=0, title="Chapter One", source_text="Low latency matters.")
            db.add(chapter)
            await db.flush()
            block = Block(chapter_id=chapter.id, position=0, block_type="paragraph", source_text="Low latency matters.")
            db.add(block)
            await db.flush()
            source_text = "Low latency matters."
            segment = Segment(
                chapter_id=chapter.id,
                block_id=block.id,
                position=0,
                source_text=source_text,
                source_hash=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            )
            db.add(segment)
            await db.commit()

            config = {
                "stages": [
                    {
                        "provider": "fake-stage4",
                        "model": "translator-test",
                        "role": "translator",
                        "temperature": 0.0,
                        "max_output_tokens": 1000,
                    }
                ],
                "qa_evaluators": [
                    {
                        "provider": "fake-stage4",
                        "model": "qa-test",
                        "weight": 1.0,
                        "temperature": 0.0,
                        "max_output_tokens": 1000,
                    }
                ],
                "max_retries": 0,
                "force": False,
                "stop_on_error": False,
                "min_quality_score": 80,
            }
            job = await create_job(
                db,
                book_id=book.id,
                chapter_id=None,
                target_language="ru",
                config=config,
                idempotency_key="stage4-integration-idempotency",
                queue_name=queue_name,
            )
            duplicate = await create_job(
                db,
                book_id=book.id,
                chapter_id=None,
                target_language="ru",
                config=config,
                idempotency_key="stage4-integration-idempotency",
                queue_name=queue_name,
            )
            assert duplicate.id == job.id

            queued_id = await dequeue_job(queue_name=queue_name, timeout_seconds=1)
            assert queued_id == job.id
            assert await dequeue_job(queue_name=queue_name, timeout_seconds=1) is None

            finished = await process_job(db, gateway, job.id)
            assert finished.status == "completed"
            assert finished.total_segments == 2
            assert finished.completed_segments == 2
            assert finished.failed_segments == 0
            assert finished.skipped_segments == 0

            segment_count = (
                await db.execute(select(func.count(Segment.id)).where(Segment.chapter_id == chapter.id))
            ).scalar_one()
            assert segment_count == 2

            qa_rows = list((await db.execute(select(TranslationQAResult))).scalars().all())
            assert len(qa_rows) == 2
            assert all(row.overall_score == pytest.approx(91.25) for row in qa_rows)

            final_versions = list(
                (
                    await db.execute(select(TranslationVersion).where(TranslationVersion.is_final.is_(True)))
                ).scalars().all()
            )
            assert len(final_versions) == 2
            assert all(version.quality_score == pytest.approx(91.25) for version in final_versions)

            memory_rows = list((await db.execute(select(TranslationMemoryEntry))).scalars().all())
            assert len(memory_rows) == 2
            assert all(memory.quality_score == pytest.approx(91.25) for memory in memory_rows)
            assert all((memory.metadata_json or {}).get("qa_verdict") == "excellent" for memory in memory_rows)

            normalized = await load_normalized_document(
                db,
                book.id,
                Path(settings.upload_dir),
                translated=True,
            )
            assert normalized is not None
            assert normalized.chapters[0].title == "RU::Chapter One"
            assert normalized.chapters[0].blocks[0].source_text == "RU::Low latency matters."

            persisted_job = await db.get(TranslationJob, job.id)
            assert persisted_job is not None and persisted_job.status == "completed"

            await db.delete(book)
            await db.commit()
    finally:
        await redis_client.delete(queue_key, marker_key)
        await engine.dispose()


def test_stage4_translation_job_queue_qa_and_translated_export() -> None:
    asyncio.run(_run())
