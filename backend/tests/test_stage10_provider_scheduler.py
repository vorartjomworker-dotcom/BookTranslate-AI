import asyncio
import os
from decimal import Decimal

import pytest

from app.ai.rate_limits import normalize_rate_limit_headers
from app.ai.schemas import ModelResponse
from app.db import AsyncSessionLocal, engine
from app.models.provider_model_policy import ProviderModelPolicy
from app.services.provider_routing import RouteSelection, acquire_route, record_provider_feedback


def test_rate_limit_header_normalization() -> None:
    payload = normalize_rate_limit_headers(
        {
            "x-ratelimit-limit-requests": "100",
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "1m30s",
            "x-ratelimit-remaining-tokens": "1200",
            "retry-after": "2",
            "x-request-id": "req-stage10",
        }
    )
    assert payload["limit_requests"] == 100
    assert payload["remaining_requests"] == 0
    assert payload["reset_requests_seconds"] == 90
    assert payload["remaining_tokens"] == 1200
    assert payload["retry_after_seconds"] == 2
    assert payload["request_id"] == "req-stage10"


@pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL and Redis")
def test_scheduler_skips_provider_in_feedback_cooldown() -> None:
    async def run() -> None:
        class Gateway:
            def has_provider(self, name: str) -> bool:
                return name in {"openai", "kimi"}

        async with AsyncSessionLocal() as db:
            first = ProviderModelPolicy(
                provider="openai",
                model="stage10-feedback-openai",
                enabled=True,
                priority=1,
                input_cost_per_million=Decimal("1"),
                output_cost_per_million=Decimal("1"),
                metadata_json={"roles": ["translator"]},
            )
            second = ProviderModelPolicy(
                provider="kimi",
                model="stage10-feedback-kimi",
                enabled=True,
                priority=2,
                input_cost_per_million=Decimal("1"),
                output_cost_per_million=Decimal("1"),
                metadata_json={"roles": ["translator"]},
            )
            db.add_all([first, second])
            await db.commit()
            selection = RouteSelection(provider=first.provider, model=first.model, policy_id=str(first.id))
            await record_provider_feedback(
                selection,
                ModelResponse(
                    text="ok",
                    provider=first.provider,
                    model=first.model,
                    metadata={"rate_limit": {"remaining_requests": 0, "reset_requests_seconds": 60}},
                ),
            )
            chosen = await acquire_route(
                db,
                Gateway(),
                requested_provider="auto",
                requested_model=None,
                role="translator",
                routing_strategy="adaptive",
                estimated_tokens=100,
            )
            assert chosen.provider == "kimi"
            assert chosen.model == second.model
            await db.delete(first)
            await db.delete(second)
            await db.commit()
        await engine.dispose()

    asyncio.run(run())
