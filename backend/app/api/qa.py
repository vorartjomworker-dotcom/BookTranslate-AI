import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.core.config import settings
from app.db import get_db
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.translation_qa import QAEvaluator, evaluate_translation_version, qa_summary

router = APIRouter(tags=["translation-qa"])


class QAEvaluatorRequest(BaseModel):
    provider: str
    model: str
    weight: float = Field(default=1.0, gt=0)
    temperature: float | None = 0.0
    max_output_tokens: int | None = 1200


class QARequest(BaseModel):
    evaluators: list[QAEvaluatorRequest]


async def _validate(db: AsyncSession, translation_id: uuid.UUID, version_id: uuid.UUID) -> TranslationVersion:
    translation = await db.get(Translation, translation_id)
    version = await db.get(TranslationVersion, version_id)
    if translation is None or version is None or version.translation_id != translation.id:
        raise HTTPException(status_code=404, detail="Translation version not found")
    return version


@router.post("/api/translations/{translation_id}/versions/{version_id}/qa")
async def run_translation_qa(
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: QARequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _validate(db, translation_id, version_id)
    if not payload.evaluators:
        raise HTTPException(status_code=422, detail="At least one QA evaluator is required")
    gateway = ModelGateway.from_settings(settings)
    evaluators = [QAEvaluator(**item.model_dump()) for item in payload.evaluators]
    try:
        await evaluate_translation_version(db, gateway, version_id=version_id, evaluators=evaluators)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await qa_summary(db, version_id)


@router.get("/api/translations/{translation_id}/versions/{version_id}/qa")
async def get_translation_qa(
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _validate(db, translation_id, version_id)
    return await qa_summary(db, version_id)
