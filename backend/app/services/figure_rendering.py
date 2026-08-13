from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import Asset
from app.models.block import Block
from app.models.book import Book
from app.models.figure import Figure
from app.models.figure_render import FigureRender
from app.models.figure_render_job import FigureRenderJob
from app.models.segment import Segment
from app.services.job_queue import enqueue_job
from app.storage.base import StorageBackend


class NoRenderableFigureText(RuntimeError):
    pass


def _valid_bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(0.0 <= item <= 1.0 for item in (x1, y1, x2, y2)):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _pixel_box(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    left = max(0, min(width - 1, round(x1 * width)))
    top = max(0, min(height - 1, round(y1 * height)))
    right = max(left + 1, min(width, round(x2 * width)))
    bottom = max(top + 1, min(height, round(y2 * height)))
    return left, top, right, bottom


def _sample_background(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    left, top, right, bottom = box
    points = [
        (left, top),
        (max(left, right - 1), top),
        (left, max(top, bottom - 1)),
        (max(left, right - 1), max(top, bottom - 1)),
    ]
    colors = [rgb.getpixel(point) for point in points]
    return tuple(sum(color[index] for color in colors) // len(colors) for index in range(3))


def _contrast_color(background: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = background
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0, 0, 0) if luminance >= 140 else (255, 255, 255)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(settings.figure_font_path, size=size)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines() or [text]:
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            width = draw.textbbox((0, 0), candidate, font=font)[2]
            if width <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return "\n".join(lines)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int]) -> tuple[ImageFont.ImageFont, str]:
    left, top, right, bottom = box
    padding = max(0, settings.figure_render_padding_px)
    max_width = max(1, right - left - padding * 2)
    max_height = max(1, bottom - top - padding * 2)
    upper = min(settings.figure_render_max_font_size, max(settings.figure_render_min_font_size, int(max_height * 0.8)))
    for size in range(upper, settings.figure_render_min_font_size - 1, -1):
        font = _font(size)
        wrapped = _wrap_text(draw, text, font, max_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=2)
        if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
            return font, wrapped
    font = _font(settings.figure_render_min_font_size)
    return font, _wrap_text(draw, text, font, max_width)


async def _segments_for_asset(db: AsyncSession, asset_id: uuid.UUID) -> list[Segment]:
    figures = list((await db.execute(select(Figure).where(Figure.asset_id == asset_id))).scalars().all())
    block_ids = [figure.block_id for figure in figures]
    if not block_ids:
        return []
    return list(
        (
            await db.execute(
                select(Segment)
                .where(
                    Segment.block_id.in_(block_ids),
                    Segment.segment_type == "figure_text",
                    Segment.status != "superseded",
                )
                .order_by(Segment.position)
            )
        ).scalars().all()
    )


def _fingerprint(asset: Asset, target_language: str, segments: list[Segment]) -> str:
    payload = {
        "asset_sha256": asset.sha256,
        "target_language": target_language,
        "regions": [
            {
                "id": str(segment.id),
                "source_hash": segment.source_hash,
                "translation": segment.translated_text,
                "bbox": (segment.metadata_json or {}).get("bbox"),
            }
            for segment in segments
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


async def render_asset(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    asset: Asset,
    target_language: str,
) -> FigureRender:
    segments = await _segments_for_asset(db, asset.id)
    translated = [
        segment
        for segment in segments
        if segment.translated_text and _valid_bbox((segment.metadata_json or {}).get("bbox")) is not None
    ]
    if not translated:
        raise NoRenderableFigureText("No translated figure_text segments with normalized bbox are available")

    fingerprint = _fingerprint(asset, target_language, segments)
    latest = (
        await db.execute(
            select(FigureRender)
            .where(
                FigureRender.asset_id == asset.id,
                FigureRender.target_language == target_language,
                FigureRender.status == "completed",
            )
            .order_by(FigureRender.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and (latest.metadata_json or {}).get("fingerprint") == fingerprint:
        return latest

    source = await storage.get_bytes(asset.stored_filename)
    with Image.open(io.BytesIO(source)) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    rendered = 0
    overflow_regions: list[str] = []
    for segment in translated:
        normalized = _valid_bbox((segment.metadata_json or {}).get("bbox"))
        if normalized is None or not segment.translated_text:
            continue
        box = _pixel_box(normalized, image.width, image.height)
        background = _sample_background(image, box)
        draw.rectangle(box, fill=background)
        font, wrapped = _fit_text(draw, segment.translated_text, box)
        padding = max(0, settings.figure_render_padding_px)
        available_height = max(1, box[3] - box[1] - padding * 2)
        text_bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=2)
        if text_bbox[3] - text_bbox[1] > available_height:
            overflow_regions.append(str(segment.id))
        draw.multiline_text(
            (box[0] + padding, box[1] + padding),
            wrapped,
            font=font,
            fill=_contrast_color(background),
            spacing=2,
        )
        rendered += 1

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    data = output.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    key = f"renders/{asset.book_id}/{asset.id}/{uuid.uuid4()}.png"
    await storage.put_bytes(key, data, content_type="image/png")
    row = FigureRender(
        book_id=asset.book_id,
        asset_id=asset.id,
        target_language=target_language,
        status="completed",
        stored_filename=key,
        media_type="image/png",
        sha256=digest,
        rendered_regions=rendered,
        total_regions=len(segments),
        metadata_json={
            "fingerprint": fingerprint,
            "source_asset_sha256": asset.sha256,
            "overflow_segment_ids": overflow_regions,
            "renderer": "pillow-v1",
        },
    )
    db.add(row)
    await db.flush()
    return row


async def create_figure_render_job(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    asset_id: uuid.UUID | None,
    target_language: str | None,
    queue_name: str,
) -> FigureRenderJob:
    book = await db.get(Book, book_id)
    if book is None:
        raise LookupError("Book not found")
    if asset_id is not None:
        asset = await db.get(Asset, asset_id)
        if asset is None or asset.book_id != book_id:
            raise LookupError("Asset not found")
    job = FigureRenderJob(
        book_id=book_id,
        asset_id=asset_id,
        target_language=target_language or book.target_language,
        queue_name=queue_name,
        status="queued",
        metadata_json={},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await enqueue_job(job.id, queue_name=queue_name)
    return job


async def recover_figure_render_jobs(db: AsyncSession, *, queue_name: str, stale_after_seconds: int) -> int:
    stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    rows = list(
        (
            await db.execute(
                select(FigureRenderJob).where(
                    FigureRenderJob.queue_name == queue_name,
                    FigureRenderJob.status.in_(["queued", "running"]),
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
            job.current_asset_id = None
        if await enqueue_job(job.id, queue_name=queue_name):
            recovered += 1
    await db.commit()
    return recovered


async def process_figure_render_job(
    db: AsyncSession,
    storage: StorageBackend,
    job_id: uuid.UUID,
) -> FigureRenderJob:
    job = await db.get(FigureRenderJob, job_id)
    if job is None:
        raise LookupError("Figure render job not found")
    if job.status in {"completed", "completed_with_warnings", "cancelled", "failed"}:
        return job

    query = select(Asset).join(Figure, Figure.asset_id == Asset.id).where(Asset.book_id == job.book_id)
    if job.asset_id is not None:
        query = query.where(Asset.id == job.asset_id)
    assets = list((await db.execute(query.distinct().order_by(Asset.position))).scalars().all())
    job.total_assets = len(assets)
    job.status = "running"
    job.started_at = job.started_at or datetime.now(timezone.utc)
    await db.commit()

    errors: list[dict] = []
    for asset in assets:
        job.current_asset_id = asset.id
        await db.commit()
        try:
            await render_asset(db, storage, asset=asset, target_language=job.target_language)
            job.completed_assets += 1
        except NoRenderableFigureText as exc:
            job.skipped_assets += 1
            errors.append({"asset_id": str(asset.id), "kind": "skipped", "reason": str(exc)})
        except Exception as exc:
            job.failed_assets += 1
            errors.append({"asset_id": str(asset.id), "kind": "render_error", "error": str(exc)[:2000]})
        job.metadata_json = {"errors": errors}
        await db.commit()

    job.current_asset_id = None
    job.completed_at = datetime.now(timezone.utc)
    if not assets:
        job.status = "completed_with_warnings"
        job.error = "No figure assets found"
    elif job.failed_assets == len(assets):
        job.status = "failed"
        job.error = "All figure renders failed"
    elif job.failed_assets or job.skipped_assets:
        job.status = "completed_with_warnings"
    else:
        job.status = "completed"
    await db.commit()
    await db.refresh(job)
    return job
