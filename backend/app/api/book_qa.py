import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.book import Book
from app.models.book_qa_report import BookQAReport
from app.models.terminology_issue import TerminologyIssue
from app.services.book_qa import build_book_qa_report

router = APIRouter(tags=["book-qa"])


class BookQARequest(BaseModel):
    target_language: str | None = None
    low_quality_threshold: float = Field(default=80.0, ge=0, le=100)


class TerminologyIssueStatus(BaseModel):
    status: str


def _report(item: BookQAReport) -> dict:
    return {
        "id": str(item.id),
        "book_id": str(item.book_id),
        "target_language": item.target_language,
        "overall_score": item.overall_score,
        "translation_coverage": item.translation_coverage,
        "average_segment_quality": item.average_segment_quality,
        "terminology_consistency": item.terminology_consistency,
        "human_review_coverage": item.human_review_coverage,
        "total_segments": item.total_segments,
        "translated_segments": item.translated_segments,
        "qa_evaluated_segments": item.qa_evaluated_segments,
        "low_quality_segments": item.low_quality_segments,
        "unresolved_reviews": item.unresolved_reviews,
        "terminology_issues": item.terminology_issues,
        "input_tokens": item.total_input_tokens,
        "output_tokens": item.total_output_tokens,
        "estimated_cost_usd": str(item.estimated_cost_usd),
        "issues": item.issues_json,
        "metadata": item.metadata_json,
        "created_at": item.created_at,
    }


@router.post("/api/books/{book_id}/qa-report")
async def create_book_qa_report(
    book_id: uuid.UUID,
    payload: BookQARequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    report = await build_book_qa_report(
        db,
        book_id=book_id,
        target_language=payload.target_language or book.target_language,
        low_quality_threshold=payload.low_quality_threshold,
    )
    return _report(report)


@router.get("/api/books/{book_id}/qa-report/latest")
async def latest_book_qa_report(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    report = (
        await db.execute(
            select(BookQAReport)
            .where(BookQAReport.book_id == book_id)
            .order_by(BookQAReport.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Book QA report not found")
    return _report(report)


@router.get("/api/books/{book_id}/terminology-issues")
async def list_terminology_issues(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = list(
        (
            await db.execute(
                select(TerminologyIssue)
                .where(TerminologyIssue.book_id == book_id)
                .order_by(TerminologyIssue.status, TerminologyIssue.created_at.desc())
            )
        ).scalars().all()
    )
    return [
        {
            "id": str(item.id),
            "segment_id": str(item.segment_id) if item.segment_id else None,
            "source_term": item.source_term,
            "expected_target_term": item.expected_target_term,
            "translated_text": item.translated_text,
            "issue_type": item.issue_type,
            "severity": item.severity,
            "status": item.status,
        }
        for item in rows
    ]


@router.post("/api/terminology-issues/{issue_id}/status")
async def set_terminology_issue_status(
    issue_id: uuid.UUID,
    payload: TerminologyIssueStatus,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.status not in {"open", "resolved", "ignored"}:
        raise HTTPException(status_code=422, detail="Status must be open, resolved or ignored")
    item = await db.get(TerminologyIssue, issue_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Terminology issue not found")
    item.status = payload.status
    await db.commit()
    return {"id": str(item.id), "status": item.status}
