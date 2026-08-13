import asyncio
import hashlib
import os

import pytest
from sqlalchemy import func, select

from app.db import AsyncSessionLocal, engine
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_quality_evaluation import TranslationQualityEvaluation
from app.models.translation_version import TranslationVersion
from app.services.quality_evaluation import evaluate_translation_quality_v2

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL integration database",
)


async def _run() -> None:
    source = "The memory pool limit is 64 MB. See https://docs.example.test/memory."
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    try:
        async with AsyncSessionLocal() as db:
            book = Book(title="Quality V2 Test", source_language="en", target_language="ru")
            db.add(book)
            await db.flush()
            chapter = Chapter(book_id=book.id, position=0, title="Chapter", source_text=source)
            db.add(chapter)
            await db.flush()
            segment = Segment(chapter_id=chapter.id, position=0, source_text=source, source_hash=source_hash)
            db.add(segment)
            await db.flush()
            db.add(
                GlossaryTerm(
                    book_id=book.id,
                    source_term="memory pool",
                    target_term="пул памяти",
                    source_language="en",
                    target_language="ru",
                )
            )
            translation = Translation(segment_id=segment.id, target_language="ru")
            db.add(translation)
            await db.flush()
            good = TranslationVersion(
                translation_id=translation.id,
                version_number=1,
                text="Пул памяти имеет лимит 64 MB. См. https://docs.example.test/memory.",
                is_final=True,
            )
            bad = TranslationVersion(
                translation_id=translation.id,
                version_number=2,
                text="Пул памяти описан в документации.",
            )
            db.add_all([good, bad])
            await db.commit()
            await db.refresh(good)
            await db.refresh(bad)

            good_eval = await evaluate_translation_quality_v2(db, version_id=good.id)
            assert good_eval.final_score >= 95
            assert good_eval.critical_fail is False
            assert good_eval.terminology_score == 100
            await db.refresh(good)
            assert good.quality_score == good_eval.final_score
            assert good.metadata_json["quality_schema"] == "quality-v2"

            bad_eval = await evaluate_translation_quality_v2(db, version_id=bad.id, judge_score=99)
            assert bad_eval.critical_fail is True
            assert bad_eval.final_score <= 59
            assert any(item["kind"] == "missing_url" for item in bad_eval.issues_json)
            await db.refresh(bad)
            assert bad.quality_score == bad_eval.final_score

            count = (
                await db.execute(
                    select(func.count(TranslationQualityEvaluation.id)).where(
                        TranslationQualityEvaluation.translation_version_id.in_([good.id, bad.id])
                    )
                )
            ).scalar_one()
            assert count == 2

            await db.delete(book)
            await db.commit()
    finally:
        await engine.dispose()


def test_quality_v2_database_round_trip() -> None:
    asyncio.run(_run())
