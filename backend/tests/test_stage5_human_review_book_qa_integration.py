import asyncio
import hashlib
import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select

import app.services.provider_routing as provider_routing
from app.ai.gateway import ModelGateway
from app.ai.providers.base import ModelProvider
from app.ai.schemas import ModelRequest, ModelResponse
from app.db import AsyncSessionLocal, engine
from app.models.block import Block
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.glossary_term import GlossaryTerm
from app.models.human_review import HumanReview
from app.models.model_run import ModelRun
from app.models.provider_model_policy import ProviderModelPolicy
from app.models.segment import Segment
from app.models.terminology_issue import TerminologyIssue
from app.models.translation_job import TranslationJob
from app.services.book_qa import build_book_qa_report
from app.services.human_review import resolve_human_review
from app.services.translation_jobs import process_job

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL integration database",
)


class FakeRedis:
    def __init__(self):
        self.values: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def incrby(self, key: str, amount: int) -> int:
        self.values[key] = self.values.get(key, 0) + amount
        return self.values[key]

    async def decrby(self, key: str, amount: int) -> int:
        self.values[key] = self.values.get(key, 0) - amount
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def set(self, key: str, value: int, ex: int | None = None) -> bool:
        self.values[key] = int(value)
        return True


class Stage5Provider(ModelProvider):
    name = "stage5"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        role = str(request.metadata.get("role"))
        if role == "qa_evaluator":
            text = json.dumps(
                {
                    "semantic_accuracy": 92,
                    "terminology": 88,
                    "completeness": 95,
                    "fluency": 90,
                    "technical_integrity": 94,
                    "style": 89,
                    "issues": ["terminology should be checked"],
                }
            )
        else:
            source = request.user_prompt.split("[SOURCE]\n", 1)[-1].split("\n\n", 1)[0]
            text = f"RU::{source}"
        return ModelResponse(
            text=text,
            provider=self.name,
            model=request.model,
            request_id=f"stage5-{role}-{request.model}",
            input_tokens=20,
            output_tokens=10,
        )


async def _run() -> None:
    gateway = ModelGateway()
    gateway.register(Stage5Provider())
    original_redis = provider_routing.redis_client
    fake_redis = FakeRedis()
    provider_routing.redis_client = fake_redis

    try:
        async with AsyncSessionLocal() as db:
            book = Book(title="Stage 5", source_language="en", target_language="ru")
            db.add(book)
            await db.flush()
            chapter = Chapter(book_id=book.id, position=0, title="Chapter One", source_text="Low latency matters.")
            db.add(chapter)
            await db.flush()
            block = Block(chapter_id=chapter.id, position=0, block_type="paragraph", source_text="Low latency matters.")
            db.add(block)
            await db.flush()
            source_text = "Low latency matters."
            segment = Segment(
                chapter_id=chapter.id,
                block_id=block.id,
                position=0,
                source_text=source_text,
                source_hash=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            )
            db.add(segment)
            db.add(
                GlossaryTerm(
                    book_id=book.id,
                    source_term="latency",
                    target_term="задержка",
                    source_language="en",
                    target_language="ru",
                )
            )
            db.add_all(
                [
                    ProviderModelPolicy(
                        provider="stage5",
                        model="translator-primary",
                        priority=1,
                        input_cost_per_million=Decimal("1"),
                        output_cost_per_million=Decimal("2"),
                        requests_per_minute=1,
                        metadata_json={"roles": ["translator"]},
                    ),
                    ProviderModelPolicy(
                        provider="stage5",
                        model="translator-fallback",
                        priority=2,
                        input_cost_per_million=Decimal("2"),
                        output_cost_per_million=Decimal("3"),
                        requests_per_minute=100,
                        metadata_json={"roles": ["translator"]},
                    ),
                    ProviderModelPolicy(
                        provider="stage5",
                        model="qa-model",
                        priority=1,
                        input_cost_per_million=Decimal("0.5"),
                        output_cost_per_million=Decimal("1"),
                        requests_per_minute=100,
                        metadata_json={"roles": ["qa_evaluator"]},
                    ),
                ]
            )
            await db.flush()
            job = TranslationJob(
                book_id=book.id,
                scope="book",
                target_language="ru",
                status="queued",
                queue_name="stage5-test",
                config_json={
                    "stages": [
                        {
                            "provider": "auto",
                            "model": None,
                            "role": "translator",
                            "temperature": 0.0,
                            "max_output_tokens": 500,
                            "routing_strategy": "priority",
                        }
                    ],
                    "qa_evaluators": [
                        {
                            "provider": "auto",
                            "model": None,
                            "weight": 1.0,
                            "temperature": 0.0,
                            "max_output_tokens": 500,
                            "routing_strategy": "priority",
                        }
                    ],
                    "max_retries": 0,
                    "human_review_below": 95,
                    "max_job_cost_usd": "1.0",
                    "max_job_input_tokens": 10000,
                    "max_job_output_tokens": 10000,
                },
                errors_json=[],
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            finished = await process_job(db, gateway, job.id)
            assert finished.status == "completed"
            assert finished.total_segments == 2
            assert finished.completed_segments == 2
            assert finished.input_tokens == 80
            assert finished.output_tokens == 40
            assert finished.estimated_cost_usd > 0

            runs = list(
                (
                    await db.execute(
                        select(ModelRun)
                        .where(ModelRun.translation_job_id == job.id)
                        .order_by(ModelRun.created_at)
                    )
                ).scalars().all()
            )
            translator_models = [item.model for item in runs if item.role == "translator"]
            assert translator_models == ["translator-primary", "translator-fallback"]
            assert all(item.estimated_cost_usd is not None for item in runs)
            cost_sum = (
                await db.execute(
                    select(func.coalesce(func.sum(ModelRun.estimated_cost_usd), 0)).where(
                        ModelRun.translation_job_id == job.id
                    )
                )
            ).scalar_one()
            assert finished.estimated_cost_usd == cost_sum

            reviews = list((await db.execute(select(HumanReview).order_by(HumanReview.created_at))).scalars().all())
            assert len(reviews) == 2
            assert all(item.status == "pending" for item in reviews)
            resolved, selected = await resolve_human_review(
                db,
                review_id=reviews[0].id,
                action="edit",
                reviewer_id="reviewer@example.com",
                edited_text="Глава один",
                notes="Edited in Stage 5 integration test",
            )
            assert resolved.status == "edited"
            assert selected is not None and selected.is_final is True
            assert selected.role == "human_reviewer"
            assert selected.text == "Глава один"

            report = await build_book_qa_report(
                db,
                book_id=book.id,
                target_language="ru",
                low_quality_threshold=80,
            )
            assert report.translation_coverage == 100.0
            assert report.average_segment_quality == pytest.approx(91.25)
            assert report.terminology_consistency == 0.0
            assert report.human_review_coverage == 50.0
            assert report.unresolved_reviews == 1
            assert report.terminology_issues == 1
            assert report.total_input_tokens == 80
            assert report.total_output_tokens == 40
            assert report.estimated_cost_usd == cost_sum
            assert 0 <= report.overall_score <= 100

            term_issues = list((await db.execute(select(TerminologyIssue))).scalars().all())
            assert len(term_issues) == 1
            assert term_issues[0].expected_target_term == "задержка"

            await db.delete(book)
            for policy in (await db.execute(select(ProviderModelPolicy))).scalars().all():
                await db.delete(policy)
            await db.commit()
    finally:
        provider_routing.redis_client = original_redis
        await engine.dispose()


def test_stage5_auto_routing_cost_human_review_and_book_qa() -> None:
    asyncio.run(_run())
