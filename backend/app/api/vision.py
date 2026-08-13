import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_min_role
from app.core.config import settings
from app.db import get_db
from app.models.app_user import AppUser
from app.models.asset import Asset
from app.models.book import Book
from app.models.vision_extraction import VisionExtraction
from app.models.vision_job import VisionJob
from app.services.vision_jobs import create_vision_job

router = APIRouter(tags=["vision"])


class VisionJobCreate(BaseModel):
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None


def _job_out(job: VisionJob) -> dict:
    return {
        "id": str(job.id),
        "book_id": str(job.book_id),
        "asset_id": str(job.asset_id) if job.asset_id else None,
        "status": job.status,
        "provider": job.provider,
        "model": job.model,
        "total_assets": job.total_assets,
        "completed_assets": job.completed_assets,
        "failed_assets": job.failed_assets,
        "current_asset_id": str(job.current_asset_id) if job.current_asset_id else None,
        "error": job.error,
        "metadata": job.metadata_json,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def _extraction_out(item: VisionExtraction) -> dict:
    return {
        "id": str(item.id),
        "asset_id": str(item.asset_id),
        "provider": item.provider,
        "model": item.model,
        "status": item.status,
        "extracted_text": item.extracted_text,
        "regions": item.regions_json,
        "request_id": item.request_id,
        "input_tokens": item.input_tokens,
        "output_tokens": item.output_tokens,
        "error": item.error,
        "created_at": item.created_at,
    }


def _resolve_config(payload: VisionJobCreate) -> tuple[str, str, str]:
    provider = (payload.provider or settings.vision_provider).strip()
    model = (payload.model or settings.vision_model or "").strip()
    if not model:
        raise HTTPException(status_code=422, detail="Vision model must be provided in request or VISION_MODEL")
    prompt = (payload.prompt or settings.vision_prompt).strip()
    return provider, model, prompt


@router.post("/api/books/{book_id}/vision-jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_book_vision_job(
    book_id: uuid.UUID,
    payload: VisionJobCreate,
    _actor: AppUser = Depends(require_min_role("translator")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await db.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")
    provider, model, prompt = _resolve_config(payload)
    job = await create_vision_job(
        db,
        book_id=book_id,
        asset_id=None,
        provider=provider,
        model=model,
        prompt=prompt,
        queue_name=settings.vision_queue_name,
    )
    return _job_out(job)


@router.post("/api/assets/{asset_id}/vision-jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_asset_vision_job(
    asset_id: uuid.UUID,
    payload: VisionJobCreate,
    _actor: AppUser = Depends(require_min_role("translator")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    provider, model, prompt = _resolve_config(payload)
    job = await create_vision_job(
        db,
        book_id=asset.book_id,
        asset_id=asset.id,
        provider=provider,
        model=model,
        prompt=prompt,
        queue_name=settings.vision_queue_name,
    )
    return _job_out(job)


@router.get("/api/vision-jobs/{job_id}")
async def get_vision_job(
    job_id: uuid.UUID,
    _actor: AppUser = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await db.get(VisionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Vision job not found")
    return _job_out(job)


@router.get("/api/books/{book_id}/vision-jobs")
async def list_book_vision_jobs(
    book_id: uuid.UUID,
    _actor: AppUser = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list((await db.execute(select(VisionJob).where(VisionJob.book_id == book_id).order_by(VisionJob.created_at.desc()))).scalars().all())
    return [_job_out(row) for row in rows]


@router.get("/api/assets/{asset_id}/vision-extractions")
async def list_asset_vision_extractions(
    asset_id: uuid.UUID,
    _actor: AppUser = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list((await db.execute(select(VisionExtraction).where(VisionExtraction.asset_id == asset_id).order_by(VisionExtraction.created_at.desc()))).scalars().all())
    return [_extraction_out(row) for row in rows]
