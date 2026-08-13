from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, require_min_role
from app.db import get_db
from app.models.app_user import AppUser
from app.models.book import Book
from app.models.book_qa_report import BookQAReport
from app.models.chapter import Chapter
from app.models.human_review import HumanReview
from app.models.segment import Segment
from app.models.terminology_issue import TerminologyIssue
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.human_review import request_human_review, resolve_human_review

router = APIRouter(tags=["workbench"])


class EditorSaveRequest(BaseModel):
    text: str = Field(min_length=1)
    reviewer_id: str | None = None
    notes: str | None = None


async def _latest_final_version(db: AsyncSession, translation_id: uuid.UUID) -> TranslationVersion | None:
    return (
        await db.execute(
            select(TranslationVersion)
            .where(TranslationVersion.translation_id == translation_id, TranslationVersion.is_final.is_(True))
            .order_by(TranslationVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/api/books/{book_id}/workbench")
async def get_book_workbench(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _actor: AppUser | DevActor = Depends(require_min_role("viewer")),
) -> dict:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    chapters = list((await db.execute(select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position))).scalars().all())
    chapter_ids = [chapter.id for chapter in chapters]
    segments = []
    if chapter_ids:
        segments = list((await db.execute(select(Segment).where(Segment.chapter_id.in_(chapter_ids)).order_by(Segment.chapter_id, Segment.position))).scalars().all())
    segment_ids = [segment.id for segment in segments]

    translations = []
    if segment_ids:
        translations = list((await db.execute(select(Translation).where(Translation.segment_id.in_(segment_ids), Translation.target_language == book.target_language))).scalars().all())
    translation_by_segment = {translation.segment_id: translation for translation in translations}
    translation_ids = [translation.id for translation in translations]

    versions = []
    if translation_ids:
        versions = list((await db.execute(select(TranslationVersion).where(TranslationVersion.translation_id.in_(translation_ids)).order_by(TranslationVersion.translation_id, TranslationVersion.version_number))).scalars().all())
    final_by_translation: dict[uuid.UUID, TranslationVersion] = {}
    for version in versions:
        if version.is_final:
            final_by_translation[version.translation_id] = version

    review_rows = []
    version_ids = [version.id for version in versions]
    if version_ids:
        review_rows = list((await db.execute(select(HumanReview).where(HumanReview.translation_version_id.in_(version_ids)))).scalars().all())
    review_by_version = {review.translation_version_id: review for review in review_rows if review.status == "pending"}

    qa = (
        await db.execute(select(BookQAReport).where(BookQAReport.book_id == book_id, BookQAReport.target_language == book.target_language).order_by(BookQAReport.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    terminology_open = (
        await db.execute(select(func.count(TerminologyIssue.id)).where(TerminologyIssue.book_id == book_id, TerminologyIssue.status == "open"))
    ).scalar_one()

    segments_by_chapter: dict[uuid.UUID, list[dict]] = {chapter.id: [] for chapter in chapters}
    for segment in segments:
        translation = translation_by_segment.get(segment.id)
        final = final_by_translation.get(translation.id) if translation else None
        review = review_by_version.get(final.id) if final else None
        segments_by_chapter.setdefault(segment.chapter_id, []).append({
            "id": str(segment.id),
            "position": segment.position,
            "type": segment.segment_type,
            "status": segment.status,
            "source_text": segment.source_text,
            "translated_text": segment.translated_text,
            "translation_id": str(translation.id) if translation else None,
            "translation_status": translation.status if translation else None,
            "final_version_id": str(final.id) if final else None,
            "quality_score": final.quality_score if final else None,
            "pending_review_id": str(review.id) if review else None,
            "metadata": dict(segment.metadata_json or {}),
        })

    return {
        "book": {
            "id": str(book.id),
            "title": book.title,
            "source_language": book.source_language,
            "target_language": book.target_language,
            "status": book.status,
            "file_format": book.file_format,
        },
        "chapters": [
            {"id": str(chapter.id), "position": chapter.position, "title": chapter.title, "segments": segments_by_chapter.get(chapter.id, [])}
            for chapter in chapters
        ],
        "qa": None if qa is None else {
            "overall_score": qa.overall_score,
            "translation_coverage": qa.translation_coverage,
            "average_segment_quality": qa.average_segment_quality,
            "terminology_consistency": qa.terminology_consistency,
            "human_review_coverage": qa.human_review_coverage,
            "low_quality_segments": qa.low_quality_segments,
            "unresolved_reviews": qa.unresolved_reviews,
            "terminology_issues": qa.terminology_issues,
            "estimated_cost_usd": str(qa.estimated_cost_usd),
        },
        "open_terminology_issues": int(terminology_open or 0),
    }


@router.post("/api/translations/{translation_id}/editor-version")
async def save_editor_version(
    translation_id: uuid.UUID,
    payload: EditorSaveRequest,
    db: AsyncSession = Depends(get_db),
    actor: AppUser | DevActor = Depends(require_min_role("translator")),
) -> dict:
    translation = await db.get(Translation, translation_id)
    if translation is None:
        raise HTTPException(status_code=404, detail="Translation not found")
    current = await _latest_final_version(db, translation_id)
    if current is None:
        raise HTTPException(status_code=409, detail="Translation has no final version to edit")
    reviewer_id = payload.reviewer_id or getattr(actor, "email", None) or "workbench-editor"
    try:
        review = await request_human_review(
            db,
            version_id=current.id,
            reviewer_id=reviewer_id,
            notes=payload.notes,
            metadata={"source": "workbench", "actor": reviewer_id},
        )
        review, selected = await resolve_human_review(
            db,
            review_id=review.id,
            action="edit",
            reviewer_id=reviewer_id,
            edited_text=payload.text,
            notes=payload.notes,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "review_id": str(review.id),
        "status": review.status,
        "version_id": str(selected.id) if selected else None,
        "text": selected.text if selected else None,
    }
