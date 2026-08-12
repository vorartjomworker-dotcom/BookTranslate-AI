from __future__ import annotations

import uuid

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.translation_memory import TranslationMemoryEntry


async def lookup_exact(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    source_hash: str | None,
    target_language: str,
    limit: int = 3,
) -> list[TranslationMemoryEntry]:
    if not source_hash:
        return []

    result = await db.execute(
        select(TranslationMemoryEntry)
        .where(
            TranslationMemoryEntry.source_hash == source_hash,
            TranslationMemoryEntry.target_language == target_language,
            TranslationMemoryEntry.approved.is_(True),
            or_(
                TranslationMemoryEntry.book_id == book_id,
                TranslationMemoryEntry.book_id.is_(None),
            ),
        )
        .order_by(
            case((TranslationMemoryEntry.book_id == book_id, 0), else_=1),
            TranslationMemoryEntry.quality_score.desc().nullslast(),
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def remember_translation(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    source_hash: str,
    source_text: str,
    target_text: str,
    source_language: str,
    target_language: str,
    origin_translation_version_id: uuid.UUID | None = None,
    quality_score: float | None = None,
) -> TranslationMemoryEntry:
    existing_result = await db.execute(
        select(TranslationMemoryEntry).where(
            TranslationMemoryEntry.book_id == book_id,
            TranslationMemoryEntry.source_hash == source_hash,
            TranslationMemoryEntry.target_language == target_language,
        )
    )
    entry = existing_result.scalar_one_or_none()
    if entry is None:
        entry = TranslationMemoryEntry(
            book_id=book_id,
            source_hash=source_hash,
            source_text=source_text,
            target_text=target_text,
            source_language=source_language,
            target_language=target_language,
            origin_translation_version_id=origin_translation_version_id,
            quality_score=quality_score,
            approved=True,
            usage_count=0,
        )
        db.add(entry)
    else:
        entry.source_text = source_text
        entry.target_text = target_text
        entry.origin_translation_version_id = origin_translation_version_id
        entry.quality_score = quality_score
        entry.approved = True
    return entry
