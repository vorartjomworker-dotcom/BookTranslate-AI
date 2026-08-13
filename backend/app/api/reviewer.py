from __future__ import annotations

import difflib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, require_min_role, require_roles
from app.db import get_db
from app.models.app_user import AppUser
from app.models.chapter import Chapter
from app.models.human_review import HumanReview
from app.models.review_comment import ReviewComment
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion

router = APIRouter(tags=["reviewer-workflow"])


class AssignReviewRequest(BaseModel):
    user_id: uuid.UUID | None = None
    priority: int = Field(default=0, ge=-100, le=100)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class CommentResolve(BaseModel):
    is_resolved: bool = True


def _actor_id(actor: AppUser | DevActor) -> uuid.UUID | None:
    return actor.id if isinstance(actor, AppUser) else None


def _assert_review_access(review: HumanReview, actor: AppUser | DevActor) -> None:
    if actor.role == "admin" or isinstance(actor, DevActor):
        return
    if review.assigned_user_id is not None and review.assigned_user_id != actor.id:
        raise HTTPException(status_code=403, detail="Review is assigned to another reviewer")


def _comment_out(comment: ReviewComment) -> dict:
    return {
        "id": str(comment.id),
        "human_review_id": str(comment.human_review_id),
        "author_user_id": str(comment.author_user_id) if comment.author_user_id else None,
        "body": comment.body,
        "is_resolved": comment.is_resolved,
        "created_at": comment.created_at,
        "updated_at": comment.updated_at,
    }


@router.get("/api/reviews/inbox")
async def review_inbox(
    review_status: str = Query(default="pending", alias="status"),
    actor: AppUser | DevActor = Depends(require_min_role("reviewer")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = (
        select(HumanReview, TranslationVersion, Translation, Segment, Chapter)
        .join(TranslationVersion, HumanReview.translation_version_id == TranslationVersion.id)
        .join(Translation, TranslationVersion.translation_id == Translation.id)
        .join(Segment, Translation.segment_id == Segment.id)
        .join(Chapter, Segment.chapter_id == Chapter.id)
        .where(HumanReview.status == review_status)
        .order_by(HumanReview.priority.desc(), HumanReview.created_at)
    )
    if actor.role != "admin" and not isinstance(actor, DevActor):
        query = query.where(or_(HumanReview.assigned_user_id == actor.id, HumanReview.assigned_user_id.is_(None)))
    rows = (await db.execute(query)).all()
    return [
        {
            "review_id": str(review.id),
            "assigned_user_id": str(review.assigned_user_id) if review.assigned_user_id else None,
            "priority": review.priority,
            "status": review.status,
            "book_id": str(chapter.book_id),
            "chapter_id": str(chapter.id),
            "chapter_title": chapter.title,
            "segment_id": str(segment.id),
            "source_text": segment.source_text,
            "translation_id": str(translation.id),
            "version_id": str(version.id),
            "version_number": version.version_number,
            "translated_text": version.text,
            "quality_score": version.quality_score,
            "created_at": review.created_at,
        }
        for review, version, translation, segment, chapter in rows
    ]


@router.post("/api/human-reviews/{review_id}/assign")
async def assign_review(
    review_id: uuid.UUID,
    payload: AssignReviewRequest,
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    review = await db.get(HumanReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Human review not found")
    user = None
    if payload.user_id is not None:
        user = await db.get(AppUser, payload.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=404, detail="Active reviewer not found")
        if user.role not in {"reviewer", "admin"}:
            raise HTTPException(status_code=422, detail="Assigned user must have reviewer or admin role")
    review.assigned_user_id = user.id if user else None
    review.reviewer_id = user.email if user else None
    review.priority = payload.priority
    await db.commit()
    return {
        "id": str(review.id),
        "assigned_user_id": str(review.assigned_user_id) if review.assigned_user_id else None,
        "reviewer_id": review.reviewer_id,
        "priority": review.priority,
    }


@router.post("/api/human-reviews/{review_id}/comments", status_code=201)
async def add_review_comment(
    review_id: uuid.UUID,
    payload: CommentCreate,
    actor: AppUser | DevActor = Depends(require_min_role("reviewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    review = await db.get(HumanReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Human review not found")
    _assert_review_access(review, actor)
    comment = ReviewComment(
        human_review_id=review.id,
        author_user_id=_actor_id(actor),
        body=payload.body.strip(),
        is_resolved=False,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return _comment_out(comment)


@router.get("/api/human-reviews/{review_id}/comments")
async def list_review_comments(
    review_id: uuid.UUID,
    actor: AppUser | DevActor = Depends(require_min_role("reviewer")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    review = await db.get(HumanReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Human review not found")
    _assert_review_access(review, actor)
    rows = list(
        (
            await db.execute(
                select(ReviewComment)
                .where(ReviewComment.human_review_id == review_id)
                .order_by(ReviewComment.created_at)
            )
        ).scalars().all()
    )
    return [_comment_out(row) for row in rows]


@router.post("/api/review-comments/{comment_id}/resolve")
async def resolve_review_comment(
    comment_id: uuid.UUID,
    payload: CommentResolve,
    actor: AppUser | DevActor = Depends(require_min_role("reviewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    comment = await db.get(ReviewComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Review comment not found")
    review = await db.get(HumanReview, comment.human_review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Human review not found")
    _assert_review_access(review, actor)
    comment.is_resolved = payload.is_resolved
    await db.commit()
    return _comment_out(comment)


@router.get("/api/translations/{translation_id}/versions/diff")
async def version_diff(
    translation_id: uuid.UUID,
    left: int = Query(..., ge=1),
    right: int = Query(..., ge=1),
    _actor: AppUser | DevActor = Depends(require_min_role("translator")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    versions = list(
        (
            await db.execute(
                select(TranslationVersion).where(
                    TranslationVersion.translation_id == translation_id,
                    TranslationVersion.version_number.in_([left, right]),
                )
            )
        ).scalars().all()
    )
    by_number = {item.version_number: item for item in versions}
    if left not in by_number or right not in by_number:
        raise HTTPException(status_code=404, detail="Translation version not found")
    left_version = by_number[left]
    right_version = by_number[right]
    word_diff = list(
        difflib.ndiff(
            left_version.text.split(),
            right_version.text.split(),
        )
    )
    ratio = difflib.SequenceMatcher(None, left_version.text, right_version.text).ratio()
    return {
        "translation_id": str(translation_id),
        "left": {
            "version_number": left_version.version_number,
            "version_id": str(left_version.id),
            "role": left_version.role,
            "text": left_version.text,
        },
        "right": {
            "version_number": right_version.version_number,
            "version_id": str(right_version.id),
            "role": right_version.role,
            "text": right_version.text,
        },
        "similarity": round(ratio * 100, 2),
        "word_diff": word_diff,
    }
