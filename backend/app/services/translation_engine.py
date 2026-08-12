from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.ai.schemas import ModelRequest
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.model_run import ModelRun
from app.models.prompt_version import PromptVersion
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.context_builder import build_translation_context
from app.services.prompt_builder import get_default_role_prompt, render_user_prompt
from app.services.translation_memory import remember_translation


@dataclass(slots=True)
class ModelStage:
    provider: str
    model: str
    role: str
    temperature: float | None = None
    max_output_tokens: int | None = 4000


async def get_or_create_translation(
    db: AsyncSession,
    *,
    segment_id: uuid.UUID,
    target_language: str,
) -> Translation:
    if await db.get(Segment, segment_id) is None:
        raise LookupError("Segment not found")

    result = await db.execute(
        select(Translation).where(
            Translation.segment_id == segment_id,
            Translation.target_language == target_language,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        translation = Translation(
            segment_id=segment_id,
            target_language=target_language,
            status="pending",
        )
        db.add(translation)
        await db.flush()
    return translation


async def _get_or_create_prompt(db: AsyncSession, role: str) -> PromptVersion:
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.role == role, PromptVersion.is_active.is_(True))
        .order_by(PromptVersion.version_number.desc())
        .limit(1)
    )
    prompt = result.scalar_one_or_none()
    if prompt is not None:
        return prompt

    system_prompt, template = get_default_role_prompt(role)
    prompt = PromptVersion(
        name=f"default_{role}",
        role=role,
        version_number=1,
        system_prompt=system_prompt,
        template=template,
        is_active=True,
        metadata_json={"source": "builtin"},
    )
    db.add(prompt)
    await db.flush()
    return prompt


async def _latest_version(db: AsyncSession, translation_id: uuid.UUID) -> TranslationVersion | None:
    result = await db.execute(
        select(TranslationVersion)
        .where(TranslationVersion.translation_id == translation_id)
        .order_by(TranslationVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _next_version_number(db: AsyncSession, translation_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.max(TranslationVersion.version_number)).where(
            TranslationVersion.translation_id == translation_id
        )
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1


async def generate_translation_version(
    db: AsyncSession,
    gateway: ModelGateway,
    *,
    segment_id: uuid.UUID,
    target_language: str,
    stage: ModelStage,
) -> tuple[Translation, TranslationVersion, ModelRun]:
    segment = await db.get(Segment, segment_id)
    if segment is None:
        raise LookupError("Segment not found")

    translation = await get_or_create_translation(
        db,
        segment_id=segment.id,
        target_language=target_language,
    )
    prompt_version = await _get_or_create_prompt(db, stage.role)
    context = await build_translation_context(
        db,
        segment_id=segment.id,
        target_language=target_language,
    )
    latest = await _latest_version(db, translation.id)
    candidate = latest.text if latest is not None else None
    user_prompt = render_user_prompt(
        context,
        role=stage.role,
        template=prompt_version.template,
        candidate_text=candidate,
    )
    request_hash = hashlib.sha256(
        (prompt_version.system_prompt + "\n" + user_prompt).encode("utf-8")
    ).hexdigest()

    run = ModelRun(
        segment_id=segment.id,
        translation_id=translation.id,
        prompt_version_id=prompt_version.id,
        provider=stage.provider,
        model=stage.model,
        role=stage.role,
        status="running",
        request_hash=request_hash,
        metadata_json={"target_language": target_language},
    )
    db.add(run)
    translation.status = "running"
    await db.commit()
    await db.refresh(run)
    await db.refresh(translation)

    request = ModelRequest(
        model=stage.model,
        system_prompt=prompt_version.system_prompt,
        user_prompt=user_prompt,
        temperature=stage.temperature,
        max_output_tokens=stage.max_output_tokens,
        metadata={"role": stage.role, "segment_id": str(segment.id)},
    )
    started = time.perf_counter()
    try:
        response = await gateway.generate(stage.provider, request)
    except Exception as exc:
        run.status = "failed"
        run.error_text = str(exc)
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        translation.status = "failed"
        await db.commit()
        raise

    run.status = "completed"
    run.provider_request_id = response.request_id
    run.input_tokens = response.input_tokens
    run.output_tokens = response.output_tokens
    run.output_text = response.text
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.metadata_json = {
        **run.metadata_json,
        "provider_metadata": response.metadata,
    }

    version = TranslationVersion(
        translation_id=translation.id,
        model_run_id=run.id,
        version_number=await _next_version_number(db, translation.id),
        text=response.text,
        role=stage.role,
        provider=response.provider,
        model=response.model,
        is_final=False,
        metadata_json={"prompt_version": prompt_version.version_number},
    )
    db.add(version)
    translation.status = "generated"
    await db.commit()
    await db.refresh(version)
    await db.refresh(run)
    await db.refresh(translation)
    return translation, version, run


async def finalize_translation_version(
    db: AsyncSession,
    *,
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
) -> TranslationVersion:
    translation = await db.get(Translation, translation_id)
    version = await db.get(TranslationVersion, version_id)
    if translation is None or version is None or version.translation_id != translation.id:
        raise LookupError("Translation version not found")

    versions_result = await db.execute(
        select(TranslationVersion).where(TranslationVersion.translation_id == translation.id)
    )
    for item in versions_result.scalars().all():
        item.is_final = item.id == version.id

    translation.status = "approved"
    translation.selected_version_number = version.version_number
    segment = await db.get(Segment, translation.segment_id)
    if segment is None:
        raise LookupError("Segment not found")
    chapter = await db.get(Chapter, segment.chapter_id)
    if chapter is None:
        raise LookupError("Chapter not found")
    book = await db.get(Book, chapter.book_id)
    if book is None:
        raise LookupError("Book not found")

    segment.translated_text = version.text
    segment.status = "translated"
    if segment.source_hash:
        await remember_translation(
            db,
            book_id=book.id,
            source_hash=segment.source_hash,
            source_text=segment.source_text,
            target_text=version.text,
            source_language=book.source_language,
            target_language=translation.target_language,
            origin_translation_version_id=version.id,
            quality_score=version.quality_score,
        )
    await db.commit()
    await db.refresh(version)
    return version


async def run_translation_pipeline(
    db: AsyncSession,
    gateway: ModelGateway,
    *,
    segment_id: uuid.UUID,
    target_language: str,
    stages: list[ModelStage],
    finalize_last: bool = True,
) -> tuple[Translation, list[TranslationVersion]]:
    if not stages:
        raise ValueError("At least one model stage is required")
    if stages[0].role != "translator":
        raise ValueError("The first pipeline stage must have role 'translator'")

    versions: list[TranslationVersion] = []
    translation: Translation | None = None
    for stage in stages:
        translation, version, _run = await generate_translation_version(
            db,
            gateway,
            segment_id=segment_id,
            target_language=target_language,
            stage=stage,
        )
        versions.append(version)

    assert translation is not None
    if finalize_last:
        versions[-1] = await finalize_translation_version(
            db,
            translation_id=translation.id,
            version_id=versions[-1].id,
        )
    return translation, versions
