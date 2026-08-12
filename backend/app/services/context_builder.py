from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book
from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.segment import Segment
from app.services.translation_memory import lookup_exact


@dataclass(slots=True)
class GlossaryMatch:
    source_term: str
    target_term: str
    notes: str | None = None


@dataclass(slots=True)
class MemoryMatch:
    source_text: str
    target_text: str
    quality_score: float | None = None


@dataclass(slots=True)
class TranslationContext:
    segment_id: uuid.UUID
    book_id: uuid.UUID
    source_language: str
    target_language: str
    chapter_title: str | None
    source_text: str
    previous_segments: list[str] = field(default_factory=list)
    next_segments: list[str] = field(default_factory=list)
    glossary: list[GlossaryMatch] = field(default_factory=list)
    memory_matches: list[MemoryMatch] = field(default_factory=list)


async def build_translation_context(
    db: AsyncSession,
    *,
    segment_id: uuid.UUID,
    target_language: str,
    neighbor_count: int = 2,
) -> TranslationContext:
    segment = await db.get(Segment, segment_id)
    if segment is None:
        raise LookupError("Segment not found")
    chapter = await db.get(Chapter, segment.chapter_id)
    if chapter is None:
        raise LookupError("Chapter not found")
    book = await db.get(Book, chapter.book_id)
    if book is None:
        raise LookupError("Book not found")

    start = max(segment.position - neighbor_count, 0)
    end = segment.position + neighbor_count
    neighbor_result = await db.execute(
        select(Segment)
        .where(
            Segment.chapter_id == chapter.id,
            Segment.position >= start,
            Segment.position <= end,
            Segment.id != segment.id,
        )
        .order_by(Segment.position)
    )
    neighbors = list(neighbor_result.scalars().all())
    previous = [item.source_text for item in neighbors if item.position < segment.position]
    following = [item.source_text for item in neighbors if item.position > segment.position]

    glossary_result = await db.execute(
        select(GlossaryTerm).where(
            GlossaryTerm.book_id == book.id,
            GlossaryTerm.target_language == target_language,
            GlossaryTerm.approved.is_(True),
            GlossaryTerm.status == "active",
        )
    )
    glossary_matches: list[GlossaryMatch] = []
    for term in glossary_result.scalars().all():
        haystack = segment.source_text if term.case_sensitive else segment.source_text.lower()
        needle = term.source_term if term.case_sensitive else term.source_term.lower()
        if needle in haystack:
            glossary_matches.append(
                GlossaryMatch(
                    source_term=term.source_term,
                    target_term=term.target_term,
                    notes=term.notes,
                )
            )

    memory_entries = await lookup_exact(
        db,
        book_id=book.id,
        source_hash=segment.source_hash,
        target_language=target_language,
    )

    return TranslationContext(
        segment_id=segment.id,
        book_id=book.id,
        source_language=book.source_language,
        target_language=target_language,
        chapter_title=chapter.title,
        source_text=segment.source_text,
        previous_segments=previous,
        next_segments=following,
        glossary=glossary_matches,
        memory_matches=[
            MemoryMatch(
                source_text=entry.source_text,
                target_text=entry.target_text,
                quality_score=entry.quality_score,
            )
            for entry in memory_entries
        ],
    )
