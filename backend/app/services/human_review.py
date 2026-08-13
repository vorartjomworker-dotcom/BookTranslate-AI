from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.human_review import HumanReview
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.translation_engine import finalize_translation_version


async def request_human_review(
    db: AsyncSession,
    *,
    version_id: uuid.UUID,
    reviewer_id: str | None = None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> HumanReview:
    version = await db.get(TranslationVersion, version_id)
    if version is None:
        raise LookupError("Translation version not found")
    existing = (
        await db.execute(
            select(HumanReview).where(
                HumanReview.translation_version_id == version_id,
                HumanReview.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    review = HumanReview(
        translation_version_id=version_id,
        reviewer_id=reviewer_id,
        status="pending",
        notes=notes,
        metadata_json=metadata or {},
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def _next_version_number(db: AsyncSession, translation_id: uuid.UUID) -> int:
    current = (
        await db.execute(
            select(func.max(TranslationVersion.version_number)).where(
                TranslationVersion.translation_id == translation_id
            )
        )
    ).scalar_one_or_none()
    return int(current or 0) + 1


async def resolve_human_review(
    db: AsyncSession,
    *,
    review_id: uuid.UUID,
    action: str,
    reviewer_id: str | None = None,
    edited_text: str | None = None,
    notes: str | None = None,
) -> tuple[HumanReview, TranslationVersion | None]:
    if action not in {"approve", "reject", "edit"}:
        raise ValueError("Human review action must be approve, reject or edit")
    review = await db.get(HumanReview, review_id)
    if review is None:
        raise LookupError("Human review not found")
    if review.status != "pending":
        raise ValueError("Human review is already resolved")
    version = await db.get(TranslationVersion, review.translation_version_id)
    if version is None:
        raise LookupError("Translation version not found")
    translation = await db.get(Translation, version.translation_id)
    if translation is None:
        raise LookupError("Translation not found")

    selected: TranslationVersion | None = version
    if action == "approve":
        selected = await finalize_translation_version(
            db,
            translation_id=translation.id,
            version_id=version.id,
        )
        review.status = "approved"
    elif action == "edit":
        if not edited_text or not edited_text.strip():
            raise ValueError("Edited review requires non-empty edited_text")
        selected = TranslationVersion(
            translation_id=translation.id,
            model_run_id=None,
            version_number=await _next_version_number(db, translation.id),
            text=edited_text.strip(),
            role="human_reviewer",
            provider="human",
            model=reviewer_id or review.reviewer_id or "human",
            quality_score=version.quality_score,
            is_final=False,
            metadata_json={"parent_version_id": str(version.id), "human_review_id": str(review.id)},
        )
        db.add(selected)
        await db.commit()
        await db.refresh(selected)
        selected = await finalize_translation_version(
            db,
            translation_id=translation.id,
            version_id=selected.id,
        )
        review.status = "edited"
        review.edited_text = edited_text.strip()
    else:
        translation.status = "needs_review"
        segment = await db.get(Segment, translation.segment_id)
        if segment is not None:
            segment.status = "needs_review"
        review.status = "rejected"
        selected = None

    review.reviewer_id = reviewer_id or review.reviewer_id
    if notes is not None:
        review.notes = notes
    review.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(review)
    return review, selected
