from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.ai.schemas import ModelRequest
from app.models.model_run import ModelRun
from app.models.prompt_version import PromptVersion
from app.models.segment import Segment
from app.models.translation import Translation
from app.models.translation_memory import TranslationMemoryEntry
from app.models.translation_qa_result import TranslationQAResult
from app.models.translation_version import TranslationVersion
from app.services.context_builder import build_translation_context
from app.services.provider_routing import acquire_route, estimate_request_tokens, estimate_response_cost, release_route

QA_WEIGHTS = {
    "semantic_accuracy": 0.30,
    "terminology": 0.20,
    "completeness": 0.15,
    "fluency": 0.15,
    "technical_integrity": 0.10,
    "style": 0.10,
}
_QA_SYSTEM = "You are an independent bilingual QA evaluator for a technical-book translation. Score fidelity, terminology, completeness, fluency, technical integrity and style. Do not rewrite the translation. Return strict JSON only."
_QA_TEMPLATE = "Evaluate the CANDIDATE against SOURCE and context. Scores must be numbers from 0 to 100. Return exactly one JSON object with keys: semantic_accuracy, terminology, completeness, fluency, technical_integrity, style, issues. issues must be an array of short strings. No markdown fences and no commentary."


@dataclass(slots=True)
class QAEvaluator:
    provider: str
    model: str | None
    weight: float = 1.0
    temperature: float | None = 0.0
    max_output_tokens: int | None = 1200
    routing_strategy: str = "priority"


def _score(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid QA score: {value!r}") from exc
    return round(max(0.0, min(100.0, numeric)), 2)


def _overall(scores: dict[str, float]) -> float:
    return round(sum(scores[key] * QA_WEIGHTS[key] for key in QA_WEIGHTS), 2)


def verdict_for_score(score: float) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    if score >= 70:
        return "acceptable"
    if score >= 60:
        return "needs_review"
    return "poor"


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("QA provider did not return a JSON object")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("QA provider returned non-object JSON")
    return payload


async def _get_or_create_qa_prompt(db: AsyncSession) -> PromptVersion:
    prompt = (
        await db.execute(
            select(PromptVersion)
            .where(PromptVersion.role == "qa_evaluator", PromptVersion.is_active.is_(True))
            .order_by(PromptVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prompt is not None:
        return prompt
    prompt = PromptVersion(
        name="default_qa_evaluator",
        role="qa_evaluator",
        version_number=1,
        system_prompt=_QA_SYSTEM,
        template=_QA_TEMPLATE,
        is_active=True,
        metadata_json={"source": "builtin", "schema": "qa-v1"},
    )
    db.add(prompt)
    await db.flush()
    return prompt


def _render_qa_prompt(context, candidate: str, template: str) -> str:
    glossary = "\n".join(f"{item.source_term} => {item.target_term}" for item in context.glossary) or "(none)"
    previous = "\n".join(context.previous_segments) or "(none)"
    next_text = "\n".join(context.next_segments) or "(none)"
    return "\n\n".join([
        template,
        f"[SOURCE LANGUAGE]\n{context.source_language}",
        f"[TARGET LANGUAGE]\n{context.target_language}",
        f"[CHAPTER]\n{context.chapter_title or '(untitled)'}",
        f"[PREVIOUS CONTEXT]\n{previous}",
        f"[NEXT CONTEXT]\n{next_text}",
        f"[GLOSSARY]\n{glossary}",
        f"[SOURCE]\n{context.source_text}",
        f"[CANDIDATE]\n{candidate}",
    ])


async def evaluate_translation_version(
    db: AsyncSession,
    gateway: ModelGateway,
    *,
    version_id: uuid.UUID,
    evaluators: list[QAEvaluator],
    translation_job_id: uuid.UUID | None = None,
) -> tuple[float, list[TranslationQAResult]]:
    if not evaluators:
        raise ValueError("At least one QA evaluator is required")
    version = await db.get(TranslationVersion, version_id)
    if version is None:
        raise LookupError("Translation version not found")
    translation = await db.get(Translation, version.translation_id)
    if translation is None:
        raise LookupError("Translation not found")
    segment = await db.get(Segment, translation.segment_id)
    if segment is None:
        raise LookupError("Segment not found")
    context = await build_translation_context(db, segment_id=segment.id, target_language=translation.target_language)
    prompt_version = await _get_or_create_qa_prompt(db)
    user_prompt = _render_qa_prompt(context, version.text, prompt_version.template)
    results: list[TranslationQAResult] = []

    for evaluator in evaluators:
        estimated_tokens = estimate_request_tokens(prompt_version.system_prompt, user_prompt, evaluator.max_output_tokens)
        route = await acquire_route(
            db,
            gateway,
            requested_provider=evaluator.provider,
            requested_model=evaluator.model,
            role="qa_evaluator",
            routing_strategy=evaluator.routing_strategy,
            estimated_tokens=estimated_tokens,
        )
        request_hash = hashlib.sha256(
            (prompt_version.system_prompt + "\n" + user_prompt + route.provider + route.model).encode("utf-8")
        ).hexdigest()
        run = ModelRun(
            segment_id=segment.id,
            translation_id=translation.id,
            translation_job_id=translation_job_id,
            prompt_version_id=prompt_version.id,
            provider=route.provider,
            model=route.model,
            role="qa_evaluator",
            status="running",
            request_hash=request_hash,
            metadata_json={
                "qa_schema": "qa-v1",
                "weight": evaluator.weight,
                "requested_provider": evaluator.provider,
                "requested_model": evaluator.model,
                "routing_strategy": evaluator.routing_strategy,
                "policy_id": route.policy_id,
            },
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        request = ModelRequest(
            model=route.model,
            system_prompt=prompt_version.system_prompt,
            user_prompt=user_prompt,
            temperature=evaluator.temperature,
            max_output_tokens=evaluator.max_output_tokens,
            metadata={"role": "qa_evaluator", "translation_version_id": str(version.id)},
        )
        started = time.perf_counter()
        try:
            response = await gateway.generate(route.provider, request)
            payload = _parse_json(response.text)
            scores = {key: _score(payload.get(key)) for key in QA_WEIGHTS}
            overall = _overall(scores)
            issues = payload.get("issues", [])
            if not isinstance(issues, list):
                issues = [str(issues)]
            issues = [str(item)[:1000] for item in issues]
        except Exception as exc:
            run.status = "failed"
            run.error_text = str(exc)
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            await db.commit()
            raise
        finally:
            await release_route(route)

        run.status = "completed"
        run.provider_request_id = response.request_id
        run.input_tokens = response.input_tokens
        run.output_tokens = response.output_tokens
        run.estimated_cost_usd = estimate_response_cost(route, response)
        run.output_text = response.text
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        qa = TranslationQAResult(
            translation_version_id=version.id,
            model_run_id=run.id,
            provider=response.provider,
            model=response.model,
            semantic_accuracy=scores["semantic_accuracy"],
            terminology=scores["terminology"],
            completeness=scores["completeness"],
            fluency=scores["fluency"],
            technical_integrity=scores["technical_integrity"],
            style=scores["style"],
            overall_score=overall,
            verdict=verdict_for_score(overall),
            issues_json=issues,
            raw_response=response.text,
            metadata_json={"evaluator_weight": evaluator.weight, "qa_schema": "qa-v1", "policy_id": route.policy_id},
        )
        db.add(qa)
        await db.commit()
        await db.refresh(qa)
        results.append(qa)

    total_weight = sum(max(0.0, evaluator.weight) for evaluator in evaluators) or float(len(evaluators))
    aggregate = round(
        sum(result.overall_score * max(0.0, evaluator.weight) for result, evaluator in zip(results, evaluators)) / total_weight,
        2,
    )
    version.quality_score = aggregate
    version.metadata_json = {
        **dict(version.metadata_json or {}),
        "qa_evaluators": len(results),
        "qa_score": aggregate,
        "qa_verdict": verdict_for_score(aggregate),
    }
    memory_rows = list(
        (
            await db.execute(
                select(TranslationMemoryEntry).where(TranslationMemoryEntry.origin_translation_version_id == version.id)
            )
        ).scalars().all()
    )
    for memory in memory_rows:
        memory.quality_score = aggregate
        memory.metadata_json = {**dict(memory.metadata_json or {}), "qa_score": aggregate, "qa_verdict": verdict_for_score(aggregate)}
    await db.commit()
    await db.refresh(version)
    return aggregate, results


async def qa_summary(db: AsyncSession, version_id: uuid.UUID) -> dict:
    version = await db.get(TranslationVersion, version_id)
    if version is None:
        raise LookupError("Translation version not found")
    rows = list(
        (
            await db.execute(
                select(TranslationQAResult)
                .where(TranslationQAResult.translation_version_id == version_id)
                .order_by(TranslationQAResult.created_at)
            )
        ).scalars().all()
    )
    if not rows:
        return {"translation_version_id": str(version_id), "score": None, "verdict": "not_evaluated", "evaluators": []}
    weights = [max(0.0, float((row.metadata_json or {}).get("evaluator_weight", 1.0))) for row in rows]
    total = sum(weights) or float(len(rows))
    score = round(sum(row.overall_score * weight for row, weight in zip(rows, weights)) / total, 2)
    return {
        "translation_version_id": str(version_id),
        "score": score,
        "verdict": verdict_for_score(score),
        "evaluators": [
            {
                "provider": row.provider,
                "model": row.model,
                "score": row.overall_score,
                "verdict": row.verdict,
                "dimensions": {
                    "semantic_accuracy": row.semantic_accuracy,
                    "terminology": row.terminology,
                    "completeness": row.completeness,
                    "fluency": row.fluency,
                    "technical_integrity": row.technical_integrity,
                    "style": row.style,
                },
                "issues": row.issues_json,
            }
            for row in rows
        ],
    }
