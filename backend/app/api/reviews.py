import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.chapter import Chapter
from app.models.human_review import HumanReview
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.human_review import request_human_review, resolve_human_review

router = APIRouter(tags=["human-review"])


class ReviewCreate(BaseModel):
    reviewer_id: str | None = None
    notes: str | None = None


class ReviewResolve(BaseModel):
    action: str
    reviewer_id: str | None = None
    edited_text: str | None = None
    notes: str | None = None


def _out(review: HumanReview) -> dict:
    return {
        "id": str(review.id),
        "translation_version_id": str(review.translation_version_id),
        "reviewer_id": review.reviewer_id,
        "status": review.status,
        "edited_text": review.edited_text,
        "notes": review.notes,
        "metadata": review.metadata_json,
        "resolved_at": review.resolved_at,
    }


@router.post("/api/translations/{translation_id}/versions/{version_id}/reviews")
async def create_review(
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    version = await db.get(TranslationVersion, version_id)
    if version is None or version.translation_id != translation_id:
        raise HTTPException(status_code=404, detail="Translation version not found")
    review = await request_human_review(
        db,
        version_id=version_id,
        reviewer_id=payload.reviewer_id,
        notes=payload.notes,
        metadata={"source": "manual"},
    )
    return _out(review)


@router.post("/api/human-reviews/{review_id}/resolve")
async def resolve_review(
    review_id: uuid.UUID,
    payload: ReviewResolve,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        review, selected = await resolve_human_review(
            db,
            review_id=review_id,
            action=payload.action,
            reviewer_id=payload.reviewer_id,
            edited_text=payload.edited_text,
            notes=payload.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    data = _out(review)
    data["selected_version_id"] = str(selected.id) if selected else None
    return data


@router.get("/api/books/{book_id}/human-reviews")
async def list_book_reviews(
    book_id: uuid.UUID,
    review_status: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = (
        select(HumanReview)
        .join(TranslationVersion, HumanReview.translation_version_id == TranslationVersion.id)
        .join(Translation, TranslationVersion.translation_id == Translation.id)
        .join(Segment, Translation.segment_id == Segment.id)
        .join(Chapter, Segment.chapter_id == Chapter.id)
        .where(Chapter.book_id == book_id)
        .order_by(HumanReview.created_at.desc())
    )
    if review_status:
        query = query.where(HumanReview.status == review_status)
    return [_out(item) for item in (await db.execute(query)).scalars().all()]
