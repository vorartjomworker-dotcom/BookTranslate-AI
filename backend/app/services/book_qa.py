from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book
from app.models.book_qa_report import BookQAReport
from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.human_review import HumanReview
from app.models.model_run import ModelRun
from app.models.segment import Segment
from app.models.terminology_issue import TerminologyIssue
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion


def _contains(text: str, term: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return term in text
    return term.casefold() in text.casefold()


async def run_terminology_audit(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    target_language: str,
) -> tuple[float, list[TerminologyIssue], int]:
    book = await db.get(Book, book_id)
    if book is None:
        raise LookupError("Book not found")
    await db.execute(
        delete(TerminologyIssue).where(
            TerminologyIssue.book_id == book_id,
            TerminologyIssue.status == "open",
        )
    )
    terms = list(
        (
            await db.execute(
                select(GlossaryTerm).where(
                    GlossaryTerm.book_id == book_id,
                    GlossaryTerm.target_language == target_language,
                    GlossaryTerm.approved.is_(True),
                    GlossaryTerm.status == "active",
                )
            )
        ).scalars().all()
    )
    segments = list(
        (
            await db.execute(
                select(Segment)
                .join(Chapter, Segment.chapter_id == Chapter.id)
                .where(Chapter.book_id == book_id)
            )
        ).scalars().all()
    )

    opportunities = 0
    issues: list[TerminologyIssue] = []
    for term in terms:
        for segment in segments:
            if not _contains(segment.source_text or "", term.source_term, term.case_sensitive):
                continue
            opportunities += 1
            translated = segment.translated_text or ""
            if translated and _contains(translated, term.target_term, term.case_sensitive):
                continue
            issue = TerminologyIssue(
                book_id=book_id,
                glossary_term_id=term.id,
                segment_id=segment.id,
                source_term=term.source_term,
                expected_target_term=term.target_term,
                translated_text=segment.translated_text,
                issue_type="missing_required_term",
                severity="warning" if translated else "error",
                status="open",
                metadata_json={"target_language": target_language},
            )
            db.add(issue)
            issues.append(issue)

    consistency = 100.0 if opportunities == 0 else round((opportunities - len(issues)) * 100 / opportunities, 2)
    await db.commit()
    for issue in issues:
        await db.refresh(issue)
    return consistency, issues, opportunities


async def build_book_qa_report(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    target_language: str,
    low_quality_threshold: float = 80.0,
) -> BookQAReport:
    book = await db.get(Book, book_id)
    if book is None:
        raise LookupError("Book not found")

    segments = list(
        (
            await db.execute(
                select(Segment)
                .join(Chapter, Segment.chapter_id == Chapter.id)
                .where(Chapter.book_id == book_id)
            )
        ).scalars().all()
    )
    total_segments = len(segments)
    translated_segments = sum(1 for item in segments if item.translated_text)
    translation_coverage = round(translated_segments * 100 / total_segments, 2) if total_segments else 100.0

    final_rows = list(
        (
            await db.execute(
                select(TranslationVersion, Translation)
                .join(Translation, TranslationVersion.translation_id == Translation.id)
                .join(Segment, Translation.segment_id == Segment.id)
                .join(Chapter, Segment.chapter_id == Chapter.id)
                .where(
                    Chapter.book_id == book_id,
                    Translation.target_language == target_language,
                    TranslationVersion.is_final.is_(True),
                )
            )
        ).all()
    )
    final_versions = [row[0] for row in final_rows]
    translation_ids = list({row[1].id for row in final_rows})
    scored = [float(item.quality_score) for item in final_versions if item.quality_score is not None]
    average_quality = round(sum(scored) / len(scored), 2) if scored else 0.0
    low_quality = sum(1 for score in scored if score < low_quality_threshold)

    terminology_consistency, term_issues, opportunities = await run_terminology_audit(
        db,
        book_id=book_id,
        target_language=target_language,
    )

    review_rows: list[HumanReview] = []
    if translation_ids:
        review_rows = list(
            (
                await db.execute(
                    select(HumanReview)
                    .join(
                        TranslationVersion,
                        HumanReview.translation_version_id == TranslationVersion.id,
                    )
                    .where(TranslationVersion.translation_id.in_(translation_ids))
                )
            ).scalars().all()
        )
    unresolved_reviews = sum(1 for item in review_rows if item.status == "pending")
    resolved_reviews = sum(1 for item in review_rows if item.status in {"approved", "edited", "rejected"})
    human_review_coverage = round(resolved_reviews * 100 / len(review_rows), 2) if review_rows else 100.0

    telemetry = (
        await db.execute(
            select(
                func.coalesce(func.sum(ModelRun.input_tokens), 0),
                func.coalesce(func.sum(ModelRun.output_tokens), 0),
                func.coalesce(func.sum(ModelRun.estimated_cost_usd), 0),
            )
            .join(Translation, ModelRun.translation_id == Translation.id)
            .join(Segment, Translation.segment_id == Segment.id)
            .join(Chapter, Segment.chapter_id == Chapter.id)
            .where(Chapter.book_id == book_id, Translation.target_language == target_language)
        )
    ).one()
    input_tokens = int(telemetry[0] or 0)
    output_tokens = int(telemetry[1] or 0)
    estimated_cost = Decimal(telemetry[2] or 0)

    overall = round(
        translation_coverage * 0.25
        + average_quality * 0.40
        + terminology_consistency * 0.25
        + human_review_coverage * 0.10,
        2,
    )
    issues_json = []
    if translation_coverage < 100:
        issues_json.append({"kind": "translation_coverage", "score": translation_coverage})
    if low_quality:
        issues_json.append({"kind": "low_quality_segments", "count": low_quality, "threshold": low_quality_threshold})
    if term_issues:
        issues_json.append({"kind": "terminology", "count": len(term_issues), "opportunities": opportunities})
    if unresolved_reviews:
        issues_json.append({"kind": "pending_human_reviews", "count": unresolved_reviews})

    report = BookQAReport(
        book_id=book_id,
        target_language=target_language,
        overall_score=overall,
        translation_coverage=translation_coverage,
        average_segment_quality=average_quality,
        terminology_consistency=terminology_consistency,
        human_review_coverage=human_review_coverage,
        total_segments=total_segments,
        translated_segments=translated_segments,
        qa_evaluated_segments=len(scored),
        low_quality_segments=low_quality,
        unresolved_reviews=unresolved_reviews,
        terminology_issues=len(term_issues),
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost,
        issues_json=issues_json,
        metadata_json={
            "weights": {
                "translation_coverage": 0.25,
                "average_segment_quality": 0.40,
                "terminology_consistency": 0.25,
                "human_review_coverage": 0.10,
            },
            "low_quality_threshold": low_quality_threshold,
        },
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report
