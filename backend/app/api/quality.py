import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.core.config import settings
from app.db import get_db
from app.models.translation import Translation
from app.models.translation_version import TranslationVersion
from app.services.quality_evaluation import evaluate_translation_quality_v2, quality_history
from app.services.translation_qa import QAEvaluator, evaluate_translation_version

router = APIRouter(tags=["translation-quality"])


class QualityJudgeRequest(BaseModel):
    provider: str = "auto"
    model: str | None = None
    weight: float = Field(default=1.0, gt=0)
    temperature: float | None = 0.0
    max_output_tokens: int | None = 1200
    routing_strategy: str = "priority"


class QualityV2Request(BaseModel):
    evaluators: list[QualityJudgeRequest] = Field(default_factory=list)
    deterministic_weight: float = Field(default=0.45, ge=0)
    judge_weight: float = Field(default=0.55, ge=0)
    reference: str | None = None


async def _validate(db: AsyncSession, translation_id: uuid.UUID, version_id: uuid.UUID) -> TranslationVersion:
    translation = await db.get(Translation, translation_id)
    version = await db.get(TranslationVersion, version_id)
    if translation is None or version is None or version.translation_id != translation.id:
        raise HTTPException(status_code=404, detail="Translation version not found")
    return version


def _serialize(row) -> dict:
    return {
        "id": str(row.id),
        "translation_version_id": str(row.translation_version_id),
        "score_schema": row.score_schema,
        "evaluation_mode": row.evaluation_mode,
        "deterministic_score": row.deterministic_score,
        "judge_score": row.judge_score,
        "reference_score": row.reference_score,
        "final_score": row.final_score,
        "critical_fail": row.critical_fail,
        "dimensions": {
            "completeness": row.completeness_score,
            "terminology": row.terminology_score,
            "technical_integrity": row.technical_integrity_score,
            "source_leakage": row.source_leakage_score,
            "hallucination": row.hallucination_score,
            "style": row.style_score,
        },
        "issues": row.issues_json,
        "details": row.details_json,
        "evaluator_fingerprint": row.evaluator_fingerprint,
        "created_at": row.created_at.isoformat(),
    }


@router.post("/api/translations/{translation_id}/versions/{version_id}/quality-v2")
async def run_quality_v2(
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: QualityV2Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _validate(db, translation_id, version_id)
    judge_score = None
    if payload.evaluators:
        gateway = ModelGateway.from_settings(settings)
        try:
            judge_score, _ = await evaluate_translation_version(
                db,
                gateway,
                version_id=version_id,
                evaluators=[QAEvaluator(**item.model_dump()) for item in payload.evaluators],
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        row = await evaluate_translation_quality_v2(
            db,
            version_id=version_id,
            judge_score=judge_score,
            deterministic_weight=payload.deterministic_weight,
            judge_weight=payload.judge_weight,
            reference=payload.reference,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(row)


@router.get("/api/translations/{translation_id}/versions/{version_id}/quality-v2")
async def get_quality_v2(
    translation_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _validate(db, translation_id, version_id)
    rows = await quality_history(db, version_id)
    return {
        "translation_version_id": str(version_id),
        "latest": _serialize(rows[0]) if rows else None,
        "history": [_serialize(item) for item in rows],
    }
