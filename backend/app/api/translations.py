import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.core.config import settings
from app.db import get_db
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.context_builder import build_translation_context
from app.services.translation_engine import (
    ModelStage,
    finalize_translation_version,
    generate_translation_version,
    get_or_create_translation,
    run_translation_pipeline,
)


router = APIRouter(prefix="/api", tags=["translations"])


class TranslationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    segment_id: uuid.UUID
    target_language: str
    status: str
    selected_version_number: int | None


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    translation_id: uuid.UUID
    version_number: int
    text: str
    role: str
    provider: str | None
    model: str | None
    quality_score: float | None
    is_final: bool


class GenerateRequest(BaseModel):
    provider: str
    model: str
    target_language: str = Field(default="ru", min_length=2, max_length=20)
    role: str = "translator"
    temperature: float | None = 0.2
    max_output_tokens: int | None = 4000
    finalize: bool = False


class PipelineStageRequest(BaseModel):
    provider: str
    model: str
    role: str
    temperature: float | None = 0.2
    max_output_tokens: int | None = 4000


class PipelineRequest(BaseModel):
    target_language: str = Field(default="ru", min_length=2, max_length=20)
    stages: list[PipelineStageRequest]
    finalize_last: bool = True


def get_gateway() -> ModelGateway:
    return ModelGateway.from_settings(settings)


@router.post("/segments/{segment_id}/translations", response_model=TranslationResponse)
async def ensure_translation(
    segment_id: uuid.UUID,
    target_language: str = "ru",
    db: AsyncSession = Depends(get_db),
) -> Translation:
    try:
        translation = await get_or_create_translation(
            db,
            segment_id=segment_id,
            target_language=target_language,
        )
        await db.commit()
        await db.refresh(translation)
        return translation
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/segments/{segment_id}/translations", response_model=list[TranslationResponse])
async def list_translations(
    segment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[Translation]:
    result = await db.execute(
        select(Translation).where(Translation.segment_id == segment_id)
    )
    return list(result.scalars().all())


@router.get("/segments/{segment_id}/translation-context")
async def translation_context(
    segment_id: uuid.UUID,
    target_language: str = "ru",
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        context = await build_translation_context(
            db,
            segment_id=segment_id,
            target_language=target_language,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "segment_id": str(context.segment_id),
        "book_id": str(context.book_id),
        "source_language": context.source_language,
        "target_language": context.target_language,
        "chapter_title": context.chapter_title,
        "source_text": context.source_text,
        "previous_segments": context.previous_segments,
        "next_segments": context.next_segments,
        "glossary": [item.__dict__ for item in context.glossary],
        "memory_matches": [item.__dict__ for item in context.memory_matches],
    }


@router.post("/segments/{segment_id}/translate", response_model=VersionResponse)
async def generate_translation(
    segment_id: uuid.UUID,
    payload: GenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslationVersion:
    gateway = get_gateway()
    try:
        translation, version, _run = await generate_translation_version(
            db,
            gateway,
            segment_id=segment_id,
            target_language=payload.target_language,
            stage=ModelStage(
                provider=payload.provider,
                model=payload.model,
                role=payload.role,
                temperature=payload.temperature,
                max_output_tokens=payload.max_output_tokens,
            ),
        )
        if payload.finalize:
            version = await finalize_translation_version(
                db,
                translation_id=translation.id,
                version_id=version.id,
            )
        return version
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/segments/{segment_id}/translate/pipeline", response_model=list[VersionResponse])
async def generate_pipeline(
    segment_id: uuid.UUID,
    payload: PipelineRequest,
    db: AsyncSession = Depends(get_db),
) -> list[TranslationVersion]:
    gateway = get_gateway()
    try:
        _translation, versions = await run_translation_pipeline(
            db,
            gateway,
            segment_id=segment_id,
            target_language=payload.target_language,
            stages=[ModelStage(**stage.model_dump()) for stage in payload.stages],
            finalize_last=payload.finalize_last,
        )
        return versions
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/translations/{translation_id}/versions/{version_id}/finalize", response_model=VersionResponse)
async def finalize_version(
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TranslationVersion:
    try:
        return await finalize_translation_version(
            db,
            translation_id=translation_id,
            version_id=version_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
