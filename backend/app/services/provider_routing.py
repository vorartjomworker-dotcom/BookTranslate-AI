from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.ai.rate_limits import normalize_rate_limit_headers
from app.ai.schemas import ModelResponse
from app.core.config import settings
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
    feedback_key: str | None = None


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


def _feedback_key(provider: str, model: str) -> str:
    digest = hashlib.sha256(f"{provider}/{model}".encode("utf-8")).hexdigest()[:24]
    return f"booktranslate:provider-feedback:{digest}"


async def _load_feedback(provider: str, model: str) -> dict:
    try:
        raw = await redis_client.get(_feedback_key(provider, model))
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _feedback_block_reason(feedback: dict, estimated_tokens: int) -> str | None:
    now = time.time()
    cooldown_until = float(feedback.get("cooldown_until") or 0)
    if cooldown_until > now:
        return f"provider cooldown for {max(1, int(cooldown_until - now))}s"
    remaining_requests = feedback.get("remaining_requests")
    if remaining_requests is not None and int(remaining_requests) < max(0, settings.provider_min_remaining_requests):
        return "provider reports no remaining request capacity"
    remaining_tokens = feedback.get("remaining_tokens")
    if remaining_tokens is not None and estimated_tokens > 0 and int(remaining_tokens) < estimated_tokens:
        return "provider reports insufficient remaining token capacity"
    return None


async def record_provider_feedback(selection: RouteSelection, response: ModelResponse) -> None:
    rate_limit = dict((response.metadata or {}).get("rate_limit") or {})
    if not rate_limit:
        return
    payload = {**rate_limit, "provider": selection.provider, "model": selection.model, "observed_at": time.time()}
    retry_after = float(rate_limit.get("retry_after_seconds") or 0)
    remaining_requests = rate_limit.get("remaining_requests")
    remaining_tokens = rate_limit.get("remaining_tokens")
    reset_requests = float(rate_limit.get("reset_requests_seconds") or 0)
    reset_tokens = float(rate_limit.get("reset_tokens_seconds") or 0)
    cooldown = retry_after
    if remaining_requests is not None and int(remaining_requests) < max(0, settings.provider_min_remaining_requests):
        cooldown = max(cooldown, reset_requests or settings.provider_cooldown_default_seconds)
    if remaining_tokens is not None and int(remaining_tokens) <= 0:
        cooldown = max(cooldown, reset_tokens or settings.provider_cooldown_default_seconds)
    if cooldown > 0:
        payload["cooldown_until"] = time.time() + cooldown
    try:
        await redis_client.set(
            selection.feedback_key or _feedback_key(selection.provider, selection.model),
            json.dumps(payload, separators=(",", ":")),
            ex=max(30, settings.provider_feedback_ttl_seconds),
        )
    except Exception:
        pass


async def record_provider_error(selection: RouteSelection, exc: Exception) -> None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    status_code = getattr(response, "status_code", None)
    rate_limit = normalize_rate_limit_headers(headers or {})
    if status_code != 429 and not rate_limit.get("retry_after_seconds"):
        return
    cooldown = float(rate_limit.get("retry_after_seconds") or settings.provider_cooldown_default_seconds)
    payload = {
        **rate_limit,
        "provider": selection.provider,
        "model": selection.model,
        "status_code": status_code,
        "observed_at": time.time(),
        "cooldown_until": time.time() + max(1.0, cooldown),
    }
    try:
        await redis_client.set(
            selection.feedback_key or _feedback_key(selection.provider, selection.model),
            json.dumps(payload, separators=(",", ":")),
            ex=max(30, settings.provider_feedback_ttl_seconds),
        )
    except Exception:
        pass


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


def _selection(policy: ProviderModelPolicy, reserved: str | None | bool) -> RouteSelection:
    return RouteSelection(
        provider=policy.provider,
        model=policy.model,
        policy_id=str(policy.id),
        input_cost_per_million=policy.input_cost_per_million,
        output_cost_per_million=policy.output_cost_per_million,
        concurrency_key=reserved if isinstance(reserved, str) else None,
        feedback_key=_feedback_key(policy.provider, policy.model),
    )


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
        feedback = await _load_feedback(requested_provider, requested_model)
        reason = _feedback_block_reason(feedback, estimated_tokens)
        if reason:
            raise RuntimeError(f"Provider {requested_provider}/{requested_model} unavailable: {reason}")
        policy = (
            await db.execute(
                select(ProviderModelPolicy).where(
                    ProviderModelPolicy.provider == requested_provider,
                    ProviderModelPolicy.model == requested_model,
                )
            )
        ).scalar_one_or_none()
        if policy is None:
            return RouteSelection(
                provider=requested_provider,
                model=requested_model,
                feedback_key=_feedback_key(requested_provider, requested_model),
            )
        if not policy.enabled:
            raise RuntimeError(f"Model policy {requested_provider}/{requested_model} is disabled")
        reserved = await _reserve(policy, estimated_tokens)
        if reserved is False:
            raise RuntimeError(f"Rate/concurrency limit reached for {requested_provider}/{requested_model}")
        selection = _selection(policy, reserved)
        selection.reserved_tokens = estimated_tokens
        return selection

    policies = list(
        (
            await db.execute(
                select(ProviderModelPolicy).where(ProviderModelPolicy.enabled.is_(True))
            )
        ).scalars().all()
    )
    candidates: list[tuple[ProviderModelPolicy, dict]] = []
    for policy in policies:
        if not gateway.has_provider(policy.provider):
            continue
        roles = list((policy.metadata_json or {}).get("roles", []))
        if roles and role not in roles:
            continue
        feedback = await _load_feedback(policy.provider, policy.model)
        if _feedback_block_reason(feedback, estimated_tokens):
            continue
        candidates.append((policy, feedback))

    if routing_strategy == "cheapest":
        candidates.sort(
            key=lambda item: (
                item[0].input_cost_per_million + item[0].output_cost_per_million,
                item[0].priority,
                item[0].provider,
                item[0].model,
            )
        )
    elif routing_strategy == "adaptive":
        def adaptive_key(item: tuple[ProviderModelPolicy, dict]):
            policy, feedback = item
            remaining_requests = feedback.get("remaining_requests")
            request_capacity_penalty = -int(remaining_requests) if remaining_requests is not None else 0
            remaining_tokens = feedback.get("remaining_tokens")
            token_capacity_penalty = -int(remaining_tokens) if remaining_tokens is not None else 0
            return (
                request_capacity_penalty,
                token_capacity_penalty,
                policy.priority,
                policy.input_cost_per_million + policy.output_cost_per_million,
                policy.provider,
                policy.model,
            )
        candidates.sort(key=adaptive_key)
    else:
        candidates.sort(
            key=lambda item: (
                item[0].priority,
                item[0].input_cost_per_million + item[0].output_cost_per_million,
                item[0].provider,
                item[0].model,
            )
        )

    for policy, _feedback in candidates:
        reserved = await _reserve(policy, estimated_tokens)
        if reserved is False:
            continue
        selection = _selection(policy, reserved)
        selection.reserved_tokens = estimated_tokens
        return selection

    raise RuntimeError("No configured AI model policy currently has available capacity")
