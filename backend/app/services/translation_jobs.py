from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.section import Section
from app.models.segment import Segment
from app.models.translation_job import TranslationJob
from app.services.job_queue import enqueue_job
from app.services.translation_engine import ModelStage, run_translation_pipeline
from app.services.translation_qa import QAEvaluator, evaluate_translation_version


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def ensure_structural_heading_segments(db: AsyncSession, book_id: uuid.UUID) -> None:
    chapters = list(
        (
            await db.execute(select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.position))
        ).scalars().all()
    )
    for chapter in chapters:
        existing = list(
            (
                await db.execute(select(Segment).where(Segment.chapter_id == chapter.id))
            ).scalars().all()
        )
        structural_keys = {
            str((segment.metadata_json or {}).get("structural_key"))
            for segment in existing
            if (segment.metadata_json or {}).get("structural_key")
        }
        used_positions = {segment.position for segment in existing}
        next_position = -100000

        def allocate_position() -> int:
            nonlocal next_position
            while next_position in used_positions:
                next_position += 1
            value = next_position
            used_positions.add(value)
            next_position += 1
            return value

        if chapter.title:
            key = f"chapter:{chapter.id}"
            if key not in structural_keys:
                db.add(
                    Segment(
                        chapter_id=chapter.id,
                        block_id=None,
                        position=allocate_position(),
                        segment_type="heading",
                        source_text=chapter.title,
                        source_hash=_hash_text(chapter.title),
                        status="pending",
                        metadata_json={"structural_key": key, "structural_kind": "chapter_title"},
                    )
                )

        sections = list(
            (
                await db.execute(
                    select(Section).where(Section.chapter_id == chapter.id).order_by(Section.position)
                )
            ).scalars().all()
        )
        for section in sections:
            key = f"section:{section.id}"
            if section.title and key not in structural_keys:
                db.add(
                    Segment(
                        chapter_id=chapter.id,
                        block_id=None,
                        position=allocate_position(),
                        segment_type="heading",
                        source_text=section.title,
                        source_hash=_hash_text(section.title),
                        status="pending",
                        metadata_json={
                            "structural_key": key,
                            "structural_kind": "section_title",
                            "section_id": str(section.id),
                        },
                    )
                )
    await db.commit()


async def create_job(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    chapter_id: uuid.UUID | None,
    target_language: str,
    config: dict,
    idempotency_key: str | None = None,
    queue_name: str = "translation",
) -> TranslationJob:
    book = await db.get(Book, book_id)
    if book is None:
        raise LookupError("Book not found")
    if chapter_id is not None:
        chapter = await db.get(Chapter, chapter_id)
        if chapter is None or chapter.book_id != book_id:
            raise LookupError("Chapter not found")
    if idempotency_key:
        existing = (
            await db.execute(select(TranslationJob).where(TranslationJob.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    job = TranslationJob(
        book_id=book_id,
        chapter_id=chapter_id,
        scope="chapter" if chapter_id else "book",
        target_language=target_language,
        status="queued",
        queue_name=queue_name,
        idempotency_key=idempotency_key,
        config_json=config,
        errors_json=[],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await enqueue_job(job.id, queue_name=queue_name)
    return job


async def recover_jobs(
    db: AsyncSession,
    *,
    queue_name: str = "translation",
    stale_after_seconds: int = 900,
) -> int:
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(seconds=stale_after_seconds)
    rows = list(
        (
            await db.execute(
                select(TranslationJob).where(
                    TranslationJob.queue_name == queue_name,
                    TranslationJob.status.in_(["queued", "running"]),
                )
            )
        ).scalars().all()
    )
    recovered = 0
    for job in rows:
        if job.status == "running" and job.updated_at and job.updated_at > stale_cutoff:
            continue
        if job.status == "running":
            job.status = "queued"
            job.current_segment_id = None
        if await enqueue_job(job.id, queue_name=queue_name):
            recovered += 1
    await db.commit()
    return recovered


def _stages(config: dict) -> list[ModelStage]:
    stages = [ModelStage(**item) for item in config.get("stages", [])]
    if not stages:
        raise ValueError("Translation job requires at least one model stage")
    if stages[0].role != "translator":
        raise ValueError("First model stage must be translator")
    return stages


def _evaluators(config: dict) -> list[QAEvaluator]:
    return [QAEvaluator(**item) for item in config.get("qa_evaluators", [])]


async def _segments_for_job(db: AsyncSession, job: TranslationJob) -> list[Segment]:
    query = select(Segment).join(Chapter, Segment.chapter_id == Chapter.id).where(Chapter.book_id == job.book_id)
    if job.chapter_id is not None:
        query = query.where(Chapter.id == job.chapter_id)
    query = query.order_by(Chapter.position, Segment.position)
    return list((await db.execute(query)).scalars().all())


async def process_job(db: AsyncSession, gateway: ModelGateway, job_id: uuid.UUID) -> TranslationJob:
    job = await db.get(TranslationJob, job_id)
    if job is None:
        raise LookupError("Translation job not found")
    if job.status in {"completed", "completed_with_warnings", "cancelled"}:
        return job

    await ensure_structural_heading_segments(db, job.book_id)
    await db.refresh(job)
    segments = await _segments_for_job(db, job)
    job.total_segments = len(segments)
    job.status = "running"
    job.started_at = job.started_at or datetime.now(timezone.utc)
    await db.commit()

    config = dict(job.config_json or {})
    stages = _stages(config)
    evaluators = _evaluators(config)
    force = bool(config.get("force", False))
    max_retries = max(0, int(config.get("max_retries", 2)))
    stop_on_error = bool(config.get("stop_on_error", False))
    min_quality_score = config.get("min_quality_score")
    errors = list(job.errors_json or [])

    for segment in segments:
        await db.refresh(job)
        if job.cancellation_requested:
            job.status = "cancelled"
            job.current_segment_id = None
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return job

        job.current_segment_id = segment.id
        await db.commit()

        if not force and segment.status == "translated" and segment.translated_text:
            job.skipped_segments += 1
            await db.commit()
            continue

        last_error: Exception | None = None
        versions = []
        for attempt in range(max_retries + 1):
            try:
                _translation, versions = await run_translation_pipeline(
                    db,
                    gateway,
                    segment_id=segment.id,
                    target_language=job.target_language,
                    stages=stages,
                    finalize_last=True,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 8))

        if last_error is not None:
            job.failed_segments += 1
            errors.append({"segment_id": str(segment.id), "kind": "translation_error", "error": str(last_error)[:2000]})
            job.errors_json = errors
            await db.commit()
            if stop_on_error:
                job.status = "failed"
                job.current_segment_id = None
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return job
            continue

        if versions and evaluators:
            try:
                score, _results = await evaluate_translation_version(
                    db,
                    gateway,
                    version_id=versions[-1].id,
                    evaluators=evaluators,
                )
                if min_quality_score is not None and score < float(min_quality_score):
                    errors.append(
                        {
                            "segment_id": str(segment.id),
                            "kind": "low_quality",
                            "score": score,
                            "minimum": float(min_quality_score),
                        }
                    )
                    job.errors_json = errors
            except Exception as exc:
                errors.append({"segment_id": str(segment.id), "kind": "qa_error", "error": str(exc)[:2000]})
                job.errors_json = errors

        job.completed_segments += 1
        await db.commit()

    job.current_segment_id = None
    job.completed_at = datetime.now(timezone.utc)
    job.status = "completed_with_warnings" if job.failed_segments or errors else "completed"
    job.errors_json = errors
    await db.commit()
    await db.refresh(job)
    return job
