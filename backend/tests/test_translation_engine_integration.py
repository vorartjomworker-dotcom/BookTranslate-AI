import asyncio
import hashlib
import os

import pytest
from sqlalchemy import func, select

from app.ai.gateway import ModelGateway
from app.ai.providers.base import ModelProvider
from app.ai.schemas import ModelRequest, ModelResponse
from app.db import AsyncSessionLocal, engine
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.model_run import ModelRun
from app.models.segment import Segment
from app.models.translation_memory import TranslationMemoryEntry
from app.services.context_builder import build_translation_context
from app.services.translation_engine import ModelStage, run_translation_pipeline


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL integration database",
)


class FakeProvider(ModelProvider):
    name = "fake"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        role = str(request.metadata.get("role"))
        if role != "translator":
            assert "[CANDIDATE]" in request.user_prompt
        return ModelResponse(
            text=f"{role}-result",
            provider=self.name,
            model=request.model,
            request_id=f"run-{role}",
            input_tokens=10,
            output_tokens=3,
        )


async def _translation_round_trip() -> None:
    gateway = ModelGateway()
    gateway.register(FakeProvider())

    source_text = "The lock-free queue reduces latency."
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    try:
        async with AsyncSessionLocal() as db:
            book = Book(title="Translation Test", source_language="en", target_language="ru")
            db.add(book)
            await db.flush()
            chapter = Chapter(book_id=book.id, position=0, title="Chapter 1", source_text=source_text)
            db.add(chapter)
            await db.flush()
            segment = Segment(
                chapter_id=chapter.id,
                position=0,
                source_text=source_text,
                source_hash=source_hash,
            )
            db.add(segment)
            db.add(
                GlossaryTerm(
                    book_id=book.id,
                    source_term="lock-free queue",
                    target_term="безблокировочная очередь",
                    source_language="en",
                    target_language="ru",
                )
            )
            await db.commit()
            await db.refresh(segment)

            translation, versions = await run_translation_pipeline(
                db,
                gateway,
                segment_id=segment.id,
                target_language="ru",
                stages=[
                    ModelStage(provider="fake", model="fake-model", role="translator"),
                    ModelStage(provider="fake", model="fake-model", role="reviewer"),
                    ModelStage(provider="fake", model="fake-model", role="finalizer"),
                ],
                finalize_last=True,
            )

            assert translation.status == "approved"
            assert [version.version_number for version in versions] == [1, 2, 3]
            assert versions[-1].is_final is True
            assert versions[-1].text == "finalizer-result"

            await db.refresh(segment)
            assert segment.status == "translated"
            assert segment.translated_text == "finalizer-result"

            runs_result = await db.execute(
                select(func.count(ModelRun.id)).where(ModelRun.segment_id == segment.id)
            )
            assert runs_result.scalar_one() == 3

            memory_result = await db.execute(
                select(TranslationMemoryEntry).where(
                    TranslationMemoryEntry.book_id == book.id,
                    TranslationMemoryEntry.source_hash == source_hash,
                    TranslationMemoryEntry.target_language == "ru",
                )
            )
            memory = memory_result.scalar_one()
            assert memory.target_text == "finalizer-result"

            context = await build_translation_context(
                db,
                segment_id=segment.id,
                target_language="ru",
            )
            assert context.glossary[0].target_term == "безблокировочная очередь"
            assert context.memory_matches[0].target_text == "finalizer-result"

            await db.delete(book)
            await db.commit()
    finally:
        await engine.dispose()


def test_translation_pipeline_database_round_trip() -> None:
    asyncio.run(_translation_round_trip())
