from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import Asset
from app.models.block import Block
from app.models.figure import Figure
from app.models.segment import Segment
from app.models.vision_extraction import VisionExtraction
from app.models.vision_job import VisionJob
from app.services.job_queue import enqueue_job
from app.storage.base import StorageBackend
from app.storage.factory import create_storage
from app.storage.local import LocalStorage
from app.vision.gateway import VisionGateway


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def create_vision_job(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    asset_id: uuid.UUID | None,
    provider: str,
    model: str,
    prompt: str,
    queue_name: str,
) -> VisionJob:
    if asset_id is not None:
        asset = await db.get(Asset, asset_id)
        if asset is None or asset.book_id != book_id:
            raise LookupError("Asset not found")
    job = VisionJob(
        book_id=book_id,
        asset_id=asset_id,
        provider=provider,
        model=model,
        prompt=prompt,
        status="queued",
        metadata_json={},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await enqueue_job(job.id, queue_name=queue_name)
    return job


async def recover_vision_jobs(db: AsyncSession, *, queue_name: str, stale_after_seconds: int) -> int:
    stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    rows = list((await db.execute(select(VisionJob).where(VisionJob.status.in_(["queued", "running"])))).scalars().all())
    recovered = 0
    for job in rows:
        if job.status == "running" and job.updated_at and job.updated_at > stale_cutoff:
            continue
        if job.status == "running":
            job.status = "queued"
            job.current_asset_id = None
        if await enqueue_job(job.id, queue_name=queue_name):
            recovered += 1
    await db.commit()
    return recovered


async def _create_figure_segments(
    db: AsyncSession,
    *,
    extraction: VisionExtraction,
    asset: Asset,
    regions: list[dict],
    fallback_text: str,
) -> int:
    figures = list((await db.execute(select(Figure).where(Figure.asset_id == asset.id))).scalars().all())
    if not figures:
        return 0
    source_regions = regions or ([{"text": fallback_text, "kind": "figure_text", "bbox": None}] if fallback_text else [])
    created = 0
    for figure in figures:
        block = await db.get(Block, figure.block_id)
        if block is None:
            continue
        existing = list(
            (
                await db.execute(
                    select(Segment).where(Segment.block_id == block.id, Segment.segment_type == "figure_text")
                )
            ).scalars().all()
        )
        new_hashes = {_hash_text(str(region.get("text") or "").strip()) for region in source_regions if str(region.get("text") or "").strip()}
        for segment in existing:
            if segment.source_hash not in new_hashes and segment.status != "superseded":
                segment.status = "superseded"
        max_position = (await db.execute(select(func.max(Segment.position)).where(Segment.chapter_id == block.chapter_id))).scalar_one()
        next_position = int(max_position or 0) + 1
        existing_hashes = {segment.source_hash for segment in existing if segment.status != "superseded"}
        for index, region in enumerate(source_regions):
            text = str(region.get("text") or "").strip()
            if not text:
                continue
            digest = _hash_text(text)
            if digest in existing_hashes:
                continue
            db.add(
                Segment(
                    chapter_id=block.chapter_id,
                    block_id=block.id,
                    position=next_position,
                    segment_type="figure_text",
                    source_text=text,
                    source_hash=digest,
                    status="pending",
                    metadata_json={
                        "asset_id": str(asset.id),
                        "figure_id": str(figure.id),
                        "vision_extraction_id": str(extraction.id),
                        "region_index": index,
                        "bbox": region.get("bbox"),
                        "kind": region.get("kind") or "other",
                    },
                )
            )
            next_position += 1
            created += 1
    await db.flush()
    return created


async def _process_asset(
    db: AsyncSession,
    gateway: VisionGateway,
    *,
    asset: Asset,
    provider: str,
    model: str,
    prompt: str,
    storage: StorageBackend,
) -> VisionExtraction:
    if not (asset.media_type or "").startswith("image/"):
        raise ValueError("Asset is not an image")
    image_bytes = await storage.get_bytes(asset.stored_filename)
    result = await gateway.extract(
        provider=provider,
        model=model,
        image_bytes=image_bytes,
        media_type=asset.media_type or "image/png",
        prompt=prompt,
    )
    extraction = VisionExtraction(
        asset_id=asset.id,
        provider=result.provider,
        model=result.model or model,
        status="completed",
        extracted_text=result.text,
        regions_json=result.regions,
        raw_response_json=result.raw,
        request_id=result.request_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    db.add(extraction)
    await db.flush()
    await _create_figure_segments(db, extraction=extraction, asset=asset, regions=result.regions, fallback_text=result.text)
    return extraction


async def process_vision_job(
    db: AsyncSession,
    gateway: VisionGateway,
    job_id: uuid.UUID,
    *,
    storage: StorageBackend | None = None,
    upload_dir: str | Path | None = None,
) -> VisionJob:
    job = await db.get(VisionJob, job_id)
    if job is None:
        raise LookupError("Vision job not found")
    if job.status in {"completed", "completed_with_warnings", "cancelled", "failed"}:
        return job

    if storage is None:
        storage = LocalStorage(upload_dir) if upload_dir is not None else create_storage(settings)

    query = select(Asset).where(Asset.book_id == job.book_id)
    if job.asset_id is not None:
        query = query.where(Asset.id == job.asset_id)
    assets = [asset for asset in (await db.execute(query.order_by(Asset.position))).scalars().all() if (asset.media_type or "").startswith("image/")]
    job.total_assets = len(assets)
    job.status = "running"
    job.started_at = job.started_at or datetime.now(timezone.utc)
    await db.commit()

    errors: list[dict] = []
    for asset in assets:
        job.current_asset_id = asset.id
        await db.commit()
        try:
            await _process_asset(
                db,
                gateway,
                asset=asset,
                provider=job.provider,
                model=job.model,
                prompt=job.prompt or "Extract visible text from this figure.",
                storage=storage,
            )
            job.completed_assets += 1
        except Exception as exc:
            job.failed_assets += 1
            errors.append({"asset_id": str(asset.id), "error": str(exc)[:2000]})
            db.add(
                VisionExtraction(
                    asset_id=asset.id,
                    provider=job.provider,
                    model=job.model,
                    status="failed",
                    error=str(exc)[:4000],
                    regions_json=[],
                    raw_response_json={},
                )
            )
        job.metadata_json = {"errors": errors}
        await db.commit()

    job.current_asset_id = None
    job.completed_at = datetime.now(timezone.utc)
    if not assets:
        job.status = "completed_with_warnings"
        job.error = "No image assets found"
    elif job.failed_assets == len(assets):
        job.status = "failed"
        job.error = "All vision extractions failed"
    elif job.failed_assets:
        job.status = "completed_with_warnings"
    else:
        job.status = "completed"
    await db.commit()
    await db.refresh(job)
    return job
