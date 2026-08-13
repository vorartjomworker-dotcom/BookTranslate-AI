import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, require_min_role
from app.core.config import settings
from app.core.security import create_download_ticket
from app.db import get_db
from app.models.app_user import AppUser
from app.models.book import Book
from app.models.figure_render import FigureRender
from app.models.figure_render_job import FigureRenderJob
from app.services.figure_rendering import create_figure_render_job
from app.storage.factory import create_storage

router = APIRouter(tags=["figure-rendering"])


class FigureRenderJobRequest(BaseModel):
    asset_id: uuid.UUID | None = None
    target_language: str | None = None


def _job_payload(job: FigureRenderJob) -> dict:
    return {
        "id": str(job.id),
        "book_id": str(job.book_id),
        "asset_id": str(job.asset_id) if job.asset_id else None,
        "target_language": job.target_language,
        "status": job.status,
        "total_assets": job.total_assets,
        "completed_assets": job.completed_assets,
        "failed_assets": job.failed_assets,
        "skipped_assets": job.skipped_assets,
        "current_asset_id": str(job.current_asset_id) if job.current_asset_id else None,
        "error": job.error,
        "metadata": job.metadata_json,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


@router.post("/api/books/{book_id}/figure-render-jobs", status_code=status.HTTP_202_ACCEPTED)
async def queue_figure_render_job(
    book_id: uuid.UUID,
    payload: FigureRenderJobRequest,
    _actor: AppUser | DevActor = Depends(require_min_role("translator")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        job = await create_figure_render_job(
            db,
            book_id=book_id,
            asset_id=payload.asset_id,
            target_language=payload.target_language,
            queue_name=settings.figure_render_queue_name,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _job_payload(job)


@router.get("/api/figure-render-jobs/{job_id}")
async def get_figure_render_job(
    job_id: uuid.UUID,
    _actor: AppUser | DevActor = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await db.get(FigureRenderJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Figure render job not found")
    return _job_payload(job)


@router.get("/api/books/{book_id}/figure-renders")
async def list_figure_renders(
    book_id: uuid.UUID,
    _actor: AppUser | DevActor = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if await db.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")
    rows = list(
        (
            await db.execute(
                select(FigureRender).where(FigureRender.book_id == book_id).order_by(FigureRender.created_at.desc())
            )
        ).scalars().all()
    )
    return [
        {
            "id": str(row.id),
            "asset_id": str(row.asset_id),
            "target_language": row.target_language,
            "status": row.status,
            "media_type": row.media_type,
            "sha256": row.sha256,
            "rendered_regions": row.rendered_regions,
            "total_regions": row.total_regions,
            "metadata": row.metadata_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/api/figure-renders/{render_id}/download-ticket")
async def create_render_download_ticket(
    render_id: uuid.UUID,
    actor: AppUser | DevActor = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(FigureRender, render_id)
    if row is None or row.status != "completed":
        raise HTTPException(status_code=404, detail="Figure render not found")
    storage = create_storage(settings)
    presigned = await storage.presign_get_url(row.stored_filename, expires_seconds=settings.storage_presign_ttl_seconds)
    if presigned:
        return {"url": presigned, "expires_in": settings.storage_presign_ttl_seconds, "mode": "object-storage"}
    path = f"/api/figure-renders/{row.id}/download"
    if not settings.auth_signing_secret:
        if settings.auth_required:
            raise HTTPException(status_code=503, detail="AUTH_SIGNING_SECRET is required for protected downloads")
        return {"url": path, "expires_in": None, "mode": "application"}
    token = create_download_ticket(path=path, user_id=str(actor.id) if actor.id else None)
    return {"url": f"{path}?download_token={token}", "expires_in": settings.download_ticket_ttl_seconds, "mode": "application"}


@router.get("/api/figure-renders/{render_id}/download")
async def download_figure_render(render_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    row = await db.get(FigureRender, render_id)
    if row is None or row.status != "completed":
        raise HTTPException(status_code=404, detail="Figure render not found")
    storage = create_storage(settings)
    try:
        data = await storage.get_bytes(row.stored_filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Rendered image object not found") from exc
    return Response(
        content=data,
        media_type=row.media_type,
        headers={"Content-Disposition": f'attachment; filename="figure-{row.asset_id}-{row.target_language}.png"'},
    )
