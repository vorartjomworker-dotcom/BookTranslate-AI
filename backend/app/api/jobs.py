import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.translation_job import TranslationJob
from app.services.translation_jobs import create_job

router = APIRouter(tags=["translation-jobs"])


class StageRequest(BaseModel):
    provider: str = "auto"
    model: str | None = None
    role: str
    temperature: float | None = None
    max_output_tokens: int | None = 4000
    routing_strategy: str = "priority"


class QAEvaluatorRequest(BaseModel):
    provider: str = "auto"
    model: str | None = None
    weight: float = Field(default=1.0, gt=0)
    temperature: float | None = 0.0
    max_output_tokens: int | None = 1200
    routing_strategy: str = "priority"


class TranslationJobCreate(BaseModel):
    target_language: str | None = None
    stages: list[StageRequest]
    qa_evaluators: list[QAEvaluatorRequest] = []
    force: bool = False
    max_retries: int = Field(default=2, ge=0, le=10)
    stop_on_error: bool = False
    min_quality_score: float | None = Field(default=None, ge=0, le=100)
    human_review_below: float | None = Field(default=None, ge=0, le=100)
    max_job_cost_usd: Decimal | None = Field(default=None, gt=0)
    max_job_input_tokens: int | None = Field(default=None, gt=0)
    max_job_output_tokens: int | None = Field(default=None, gt=0)
    idempotency_key: str | None = Field(default=None, max_length=128)


class TranslationJobResponse(BaseModel):
    id: uuid.UUID
    book_id: uuid.UUID
    chapter_id: uuid.UUID | None
    scope: str
    target_language: str
    status: str
    total_segments: int
    completed_segments: int
    failed_segments: int
    skipped_segments: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    current_segment_id: uuid.UUID | None
    cancellation_requested: bool
    progress_percent: float
    errors: list


def _response(job: TranslationJob) -> TranslationJobResponse:
    processed = job.completed_segments + job.failed_segments + job.skipped_segments
    progress = round(processed * 100 / job.total_segments, 2) if job.total_segments else 0.0
    return TranslationJobResponse(
        id=job.id,
        book_id=job.book_id,
        chapter_id=job.chapter_id,
        scope=job.scope,
        target_language=job.target_language,
        status=job.status,
        total_segments=job.total_segments,
        completed_segments=job.completed_segments,
        failed_segments=job.failed_segments,
        skipped_segments=job.skipped_segments,
        input_tokens=job.input_tokens,
        output_tokens=job.output_tokens,
        estimated_cost_usd=job.estimated_cost_usd,
        current_segment_id=job.current_segment_id,
        cancellation_requested=job.cancellation_requested,
        progress_percent=progress,
        errors=list(job.errors_json or []),
    )


def _config(payload: TranslationJobCreate) -> dict:
    if not payload.stages:
        raise HTTPException(status_code=422, detail="At least one model stage is required")
    if payload.stages[0].role != "translator":
        raise HTTPException(status_code=422, detail="First model stage must have role 'translator'")
    return {
        "stages": [item.model_dump() for item in payload.stages],
        "qa_evaluators": [item.model_dump() for item in payload.qa_evaluators],
        "force": payload.force,
        "max_retries": payload.max_retries,
        "stop_on_error": payload.stop_on_error,
        "min_quality_score": payload.min_quality_score,
        "human_review_below": payload.human_review_below,
        "max_job_cost_usd": str(payload.max_job_cost_usd) if payload.max_job_cost_usd is not None else None,
        "max_job_input_tokens": payload.max_job_input_tokens,
        "max_job_output_tokens": payload.max_job_output_tokens,
    }


@router.post("/api/books/{book_id}/translation-jobs", response_model=TranslationJobResponse, status_code=202)
async def create_book_translation_job(book_id: uuid.UUID, payload: TranslationJobCreate, db: AsyncSession = Depends(get_db)) -> TranslationJobResponse:
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    job = await create_job(db, book_id=book.id, chapter_id=None, target_language=payload.target_language or book.target_language, config=_config(payload), idempotency_key=payload.idempotency_key, queue_name=settings.translation_queue_name)
    return _response(job)


@router.post("/api/chapters/{chapter_id}/translation-jobs", response_model=TranslationJobResponse, status_code=202)
async def create_chapter_translation_job(chapter_id: uuid.UUID, payload: TranslationJobCreate, db: AsyncSession = Depends(get_db)) -> TranslationJobResponse:
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    book = await db.get(Book, chapter.book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    job = await create_job(db, book_id=book.id, chapter_id=chapter.id, target_language=payload.target_language or book.target_language, config=_config(payload), idempotency_key=payload.idempotency_key, queue_name=settings.translation_queue_name)
    return _response(job)


@router.get("/api/translation-jobs/{job_id}", response_model=TranslationJobResponse)
async def get_translation_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> TranslationJobResponse:
    job = await db.get(TranslationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Translation job not found")
    return _response(job)


@router.get("/api/books/{book_id}/translation-jobs", response_model=list[TranslationJobResponse])
async def list_translation_jobs(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[TranslationJobResponse]:
    rows = list((await db.execute(select(TranslationJob).where(TranslationJob.book_id == book_id).order_by(TranslationJob.created_at.desc()))).scalars().all())
    return [_response(job) for job in rows]


@router.post("/api/translation-jobs/{job_id}/cancel", response_model=TranslationJobResponse)
async def cancel_translation_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> TranslationJobResponse:
    job = await db.get(TranslationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Translation job not found")
    if job.status in {"completed", "completed_with_warnings", "failed", "cancelled", "budget_exceeded"}:
        return _response(job)
    job.cancellation_requested = True
    if job.status == "queued":
        job.status = "cancelled"
    await db.commit()
    await db.refresh(job)
    return _response(job)
