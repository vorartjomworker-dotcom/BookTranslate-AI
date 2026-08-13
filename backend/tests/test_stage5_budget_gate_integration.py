import asyncio
import hashlib
import os
from decimal import Decimal

import pytest
from sqlalchemy import select

import app.services.provider_routing as provider_routing
from app.ai.gateway import ModelGateway
from app.ai.providers.base import ModelProvider
from app.ai.schemas import ModelRequest, ModelResponse
from app.db import AsyncSessionLocal, engine
from app.models.block import Block
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.provider_model_policy import ProviderModelPolicy
from app.models.segment import Segment
from app.models.translation_job import TranslationJob
from app.services.translation_jobs import process_job

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL integration database",
)


class FakeRedis:
    async def incr(self, key: str) -> int:
        return 1
    async def incrby(self, key: str, amount: int) -> int:
        return amount
    async def decrby(self, key: str, amount: int) -> int:
        return 0
    async def expire(self, key: str, seconds: int) -> bool:
        return True
    async def set(self, key: str, value: int, ex: int | None = None) -> bool:
        return True


class BudgetProvider(ModelProvider):
    name = "budget-test"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text="Переведено",
            provider=self.name,
            model=request.model,
            input_tokens=100,
            output_tokens=50,
        )


async def _run() -> None:
    gateway = ModelGateway()
    gateway.register(BudgetProvider())
    original = provider_routing.redis_client
    provider_routing.redis_client = FakeRedis()
    try:
        async with AsyncSessionLocal() as db:
            book = Book(title="Budget", source_language="en", target_language="ru")
            db.add(book)
            await db.flush()
            chapter = Chapter(book_id=book.id, position=0, title=None, source_text="Latency matters.")
            db.add(chapter)
            await db.flush()
            block = Block(chapter_id=chapter.id, position=0, block_type="paragraph", source_text="Latency matters.")
            db.add(block)
            await db.flush()
            source = "Latency matters."
            db.add(Segment(chapter_id=chapter.id, block_id=block.id, position=0, source_text=source, source_hash=hashlib.sha256(source.encode()).hexdigest()))
            db.add(ProviderModelPolicy(provider="budget-test", model="priced", priority=1, input_cost_per_million=Decimal("10"), output_cost_per_million=Decimal("10"), metadata_json={"roles": ["translator"]}))
            await db.flush()
            job = TranslationJob(
                book_id=book.id,
                scope="book",
                target_language="ru",
                status="queued",
                queue_name="budget-test",
                config_json={
                    "stages": [{"provider": "auto", "model": None, "role": "translator", "routing_strategy": "priority"}],
                    "qa_evaluators": [],
                    "max_retries": 0,
                    "max_job_cost_usd": "0.000001",
                },
                errors_json=[],
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            finished = await process_job(db, gateway, job.id)
            assert finished.completed_segments == 1
            assert finished.estimated_cost_usd > Decimal("0.000001")
            assert finished.status == "budget_exceeded"
            assert any(item.get("kind") == "budget_exceeded" for item in finished.errors_json)

            await db.delete(book)
            for policy in (await db.execute(select(ProviderModelPolicy))).scalars().all():
                await db.delete(policy)
            await db.commit()
    finally:
        provider_routing.redis_client = original
        await engine.dispose()


def test_budget_gate_applies_after_final_segment() -> None:
    asyncio.run(_run())
