from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.ai.schemas import ModelResponse
from app.models.provider_model_policy import ProviderModelPolicy
from app.redis_client import redis_client


@dataclass(slots=True)
class RouteSelection:
    provider: str
    model: str
    policy_id: str | None = None
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None
    concurrency_key: str | None = None
    reserved_tokens: int = 0


def estimate_request_tokens(system_prompt: str, user_prompt: str, max_output_tokens: int | None) -> int:
    approximate_input = max(1, (len(system_prompt) + len(user_prompt) + 3) // 4)
    return approximate_input + max(0, int(max_output_tokens or 0))


def estimate_response_cost(selection: RouteSelection, response: ModelResponse) -> Decimal | None:
    if selection.input_cost_per_million is None or selection.output_cost_per_million is None:
        return None
    input_tokens = Decimal(int(response.input_tokens or 0))
    output_tokens = Decimal(int(response.output_tokens or 0))
    cost = (
        input_tokens * selection.input_cost_per_million
        + output_tokens * selection.output_cost_per_million
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


async def _rollback(key: str, amount: int = 1) -> None:
    try:
        value = await redis_client.decrby(key, amount)
        if value < 0:
            await redis_client.set(key, 0, ex=65)
    except Exception:
        pass


async def _reserve(policy: ProviderModelPolicy, estimated_tokens: int) -> str | None | bool:
    prefix = f"booktranslate:route:{policy.id}"
    concurrency_key: str | None = None

    if policy.max_concurrency:
        concurrency_key = f"{prefix}:concurrency"
        current = await redis_client.incr(concurrency_key)
        await redis_client.expire(concurrency_key, 300)
        if current > policy.max_concurrency:
            await _rollback(concurrency_key)
            return False

    rpm_key: str | None = None
    if policy.requests_per_minute:
        rpm_key = f"{prefix}:rpm"
        count = await redis_client.incr(rpm_key)
        if count == 1:
            await redis_client.expire(rpm_key, 60)
        if count > policy.requests_per_minute:
            await _rollback(rpm_key)
            if concurrency_key:
                await _rollback(concurrency_key)
            return False

    tpm_key: str | None = None
    if policy.tokens_per_minute:
        tpm_key = f"{prefix}:tpm"
        count = await redis_client.incrby(tpm_key, estimated_tokens)
        if count == estimated_tokens:
            await redis_client.expire(tpm_key, 60)
        if count > policy.tokens_per_minute:
            await _rollback(tpm_key, estimated_tokens)
            if rpm_key:
                await _rollback(rpm_key)
            if concurrency_key:
                await _rollback(concurrency_key)
            return False

    return concurrency_key


async def release_route(selection: RouteSelection) -> None:
    if selection.concurrency_key:
        await _rollback(selection.concurrency_key)


async def acquire_route(
    db: AsyncSession,
    gateway: ModelGateway,
    *,
    requested_provider: str,
    requested_model: str | None,
    role: str,
    routing_strategy: str = "priority",
    estimated_tokens: int = 0,
) -> RouteSelection:
    if requested_provider != "auto":
        if not requested_model:
            raise ValueError("Explicit provider requires a model")
        if not gateway.has_provider(requested_provider):
            raise ValueError(f"AI provider '{requested_provider}' is not configured")
        policy = (
            await db.execute(
                select(ProviderModelPolicy).where(
                    ProviderModelPolicy.provider == requested_provider,
                    ProviderModelPolicy.model == requested_model,
                )
            )
        ).scalar_one_or_none()
        if policy is None:
            return RouteSelection(provider=requested_provider, model=requested_model)
        if not policy.enabled:
            raise RuntimeError(f"Model policy {requested_provider}/{requested_model} is disabled")
        reserved = await _reserve(policy, estimated_tokens)
        if reserved is False:
            raise RuntimeError(f"Rate/concurrency limit reached for {requested_provider}/{requested_model}")
        return RouteSelection(
            provider=policy.provider,
            model=policy.model,
            policy_id=str(policy.id),
            input_cost_per_million=policy.input_cost_per_million,
            output_cost_per_million=policy.output_cost_per_million,
            concurrency_key=reserved if isinstance(reserved, str) else None,
            reserved_tokens=estimated_tokens,
        )

    policies = list(
        (
            await db.execute(
                select(ProviderModelPolicy).where(ProviderModelPolicy.enabled.is_(True))
            )
        ).scalars().all()
    )
    candidates = []
    for policy in policies:
        if not gateway.has_provider(policy.provider):
            continue
        roles = list((policy.metadata_json or {}).get("roles", []))
        if roles and role not in roles:
            continue
        candidates.append(policy)

    if routing_strategy == "cheapest":
        candidates.sort(
            key=lambda item: (
                item.input_cost_per_million + item.output_cost_per_million,
                item.priority,
                item.provider,
                item.model,
            )
        )
    else:
        candidates.sort(
            key=lambda item: (
                item.priority,
                item.input_cost_per_million + item.output_cost_per_million,
                item.provider,
                item.model,
            )
        )

    for policy in candidates:
        reserved = await _reserve(policy, estimated_tokens)
        if reserved is False:
            continue
        return RouteSelection(
            provider=policy.provider,
            model=policy.model,
            policy_id=str(policy.id),
            input_cost_per_million=policy.input_cost_per_million,
            output_cost_per_million=policy.output_cost_per_million,
            concurrency_key=reserved if isinstance(reserved, str) else None,
            reserved_tokens=estimated_tokens,
        )

    raise RuntimeError("No configured AI model policy currently has available capacity")
