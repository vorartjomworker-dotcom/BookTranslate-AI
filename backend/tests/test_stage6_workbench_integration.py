import asyncio
import os

import pytest
from sqlalchemy import select

from app.api.workbench import EditorSaveRequest, get_book_workbench, save_editor_version
from app.db import AsyncSessionLocal, engine
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL integration database",
)


async def _run() -> None:
    async with AsyncSessionLocal() as db:
        book = Book(title="Stage 6 Workbench", source_language="en", target_language="ru", status="translated")
        db.add(book)
        await db.flush()
        chapter = Chapter(book_id=book.id, position=0, title="Chapter", source_text="Source text")
        db.add(chapter)
        await db.flush()
        segment = Segment(chapter_id=chapter.id, position=0, source_text="Source text", translated_text="AI text", status="translated")
        db.add(segment)
        await db.flush()
        translation = Translation(segment_id=segment.id, target_language="ru", status="approved", selected_version_number=1)
        db.add(translation)
        await db.flush()
        version = TranslationVersion(
            translation_id=translation.id,
            version_number=1,
            text="AI text",
            role="translator",
            provider="test",
            model="test-model",
            quality_score=88.0,
            is_final=True,
        )
        db.add(version)
        await db.commit()

        snapshot = await get_book_workbench(book.id, db)
        assert snapshot["book"]["title"] == "Stage 6 Workbench"
        row = snapshot["chapters"][0]["segments"][0]
        assert row["translated_text"] == "AI text"
        assert row["translation_id"] == str(translation.id)
        assert row["quality_score"] == 88.0

        saved = await save_editor_version(
            translation.id,
            EditorSaveRequest(text="Human edited text", reviewer_id="editor@test", notes="Stage 6 edit"),
            db,
        )
        assert saved["status"] == "edited"
        assert saved["text"] == "Human edited text"

        await db.refresh(segment)
        assert segment.translated_text == "Human edited text"
        versions = list((await db.execute(select(TranslationVersion).where(TranslationVersion.translation_id == translation.id).order_by(TranslationVersion.version_number))).scalars().all())
        assert len(versions) == 2
        assert versions[-1].role == "human_reviewer"
        assert versions[-1].provider == "human"
        assert versions[-1].is_final is True
        assert versions[0].is_final is False

        await db.delete(book)
        await db.commit()

    await engine.dispose()


def test_stage6_workbench_and_editor() -> None:
    asyncio.run(_run())
