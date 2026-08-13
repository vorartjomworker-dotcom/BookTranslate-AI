import asyncio
import os

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.reviewer import (
    AssignReviewRequest,
    CommentCreate,
    add_review_comment,
    assign_review,
    review_inbox,
    version_diff,
)
from app.core.auth import get_current_actor, hash_api_token
from app.db import AsyncSessionLocal, engine
from app.models.app_user import AppUser
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.human_review import request_human_review

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL integration database",
)


async def _run() -> None:
    async with AsyncSessionLocal() as db:
        admin_token = "stage7-admin-token"
        reviewer_token = "stage7-reviewer-token"
        admin = AppUser(
            email="stage7-admin@example.test",
            display_name="Stage 7 Admin",
            role="admin",
            api_token_hash=hash_api_token(admin_token),
            is_active=True,
        )
        reviewer = AppUser(
            email="stage7-reviewer@example.test",
            display_name="Stage 7 Reviewer",
            role="reviewer",
            api_token_hash=hash_api_token(reviewer_token),
            is_active=True,
        )
        db.add_all([admin, reviewer])
        await db.flush()

        actor = await get_current_actor(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=reviewer_token),
            db,
        )
        assert actor.id == reviewer.id
        assert actor.role == "reviewer"

        book = Book(title="Stage 7 Review", source_language="en", target_language="ru", status="translated")
        db.add(book)
        await db.flush()
        chapter = Chapter(book_id=book.id, position=0, title="Chapter", source_text="Source")
        db.add(chapter)
        await db.flush()
        segment = Segment(chapter_id=chapter.id, position=0, source_text="Source", translated_text="Second text", status="translated")
        db.add(segment)
        await db.flush()
        translation = Translation(segment_id=segment.id, target_language="ru", status="approved", selected_version_number=2)
        db.add(translation)
        await db.flush()
        first = TranslationVersion(
            translation_id=translation.id,
            version_number=1,
            text="First translation",
            role="translator",
            provider="test",
            model="v1",
            is_final=False,
        )
        second = TranslationVersion(
            translation_id=translation.id,
            version_number=2,
            text="Second reviewed translation",
            role="reviewer",
            provider="test",
            model="v2",
            quality_score=78.0,
            is_final=True,
        )
        db.add_all([first, second])
        await db.commit()

        review = await request_human_review(db, version_id=second.id, notes="Needs reviewer")
        assignment = await assign_review(
            review.id,
            AssignReviewRequest(user_id=reviewer.id, priority=25),
            _actor=admin,
            db=db,
        )
        assert assignment["assigned_user_id"] == str(reviewer.id)
        assert assignment["priority"] == 25

        inbox = await review_inbox(review_status="pending", actor=reviewer, db=db)
        target = next(item for item in inbox if item["review_id"] == str(review.id))
        assert target["source_text"] == "Source"
        assert target["quality_score"] == 78.0

        comment = await add_review_comment(
            review.id,
            CommentCreate(body="Terminology needs confirmation."),
            actor=reviewer,
            db=db,
        )
        assert comment["body"] == "Terminology needs confirmation."
        assert comment["author_user_id"] == str(reviewer.id)

        comparison = await version_diff(
            translation.id,
            left=1,
            right=2,
            _actor=reviewer,
            db=db,
        )
        assert comparison["left"]["text"] == "First translation"
        assert comparison["right"]["text"] == "Second reviewed translation"
        assert comparison["similarity"] < 100
        assert any(line.startswith("+") or line.startswith("-") for line in comparison["word_diff"])

        await db.delete(book)
        await db.commit()
        await db.delete(reviewer)
        await db.delete(admin)
        await db.commit()

    await engine.dispose()


def test_stage7_rbac_review_workflow() -> None:
    asyncio.run(_run())
