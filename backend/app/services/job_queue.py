from __future__ import annotations

import uuid

from prometheus_client import Counter, Gauge
from redis.asyncio import Redis

from app.redis_client import redis_client

_QUEUE_PREFIX = "booktranslate:queue"
_ENQUEUED_PREFIX = "booktranslate:queued"
_LEASE_PREFIX = "booktranslate:lease"

LEASE_CONFLICTS = Counter(
    "booktranslate_job_lease_conflicts_total",
    "Number of jobs skipped because another worker owns the active lease",
    ["queue"],
)
ACTIVE_LEASES = Gauge(
    "booktranslate_job_active_leases",
    "Number of active job leases owned by this application",
    ["queue"],
)


def _queue_key(queue_name: str) -> str:
    return f"{_QUEUE_PREFIX}:{queue_name}"


def _enqueued_key(queue_name: str) -> str:
    return f"{_ENQUEUED_PREFIX}:{queue_name}"


def _lease_key(queue_name: str, job_id: uuid.UUID) -> str:
    return f"{_LEASE_PREFIX}:{queue_name}:{job_id}"


async def enqueue_job(
    job_id: uuid.UUID,
    *,
    queue_name: str = "translation",
    redis: Redis = redis_client,
) -> bool:
    member = str(job_id)
    added = await redis.sadd(_enqueued_key(queue_name), member)
    if not added:
        return False
    try:
        await redis.rpush(_queue_key(queue_name), member)
    except Exception:
        await redis.srem(_enqueued_key(queue_name), member)
        raise
    return True


async def dequeue_job(
    *,
    queue_name: str = "translation",
    timeout_seconds: int = 5,
    redis: Redis = redis_client,
) -> uuid.UUID | None:
    item = await redis.blpop(_queue_key(queue_name), timeout=timeout_seconds)
    if item is None:
        return None
    _key, value = item
    await redis.srem(_enqueued_key(queue_name), value)
    return uuid.UUID(str(value))


async def remove_queued_marker(
    job_id: uuid.UUID,
    *,
    queue_name: str = "translation",
    redis: Redis = redis_client,
) -> None:
    await redis.srem(_enqueued_key(queue_name), str(job_id))


async def acquire_job_lease(
    job_id: uuid.UUID,
    *,
    queue_name: str,
    owner: str,
    ttl_seconds: int,
    redis: Redis = redis_client,
) -> bool:
    acquired = bool(
        await redis.set(
            _lease_key(queue_name, job_id),
            owner,
            nx=True,
            ex=max(1, ttl_seconds),
        )
    )
    if acquired:
        ACTIVE_LEASES.labels(queue=queue_name).inc()
    else:
        LEASE_CONFLICTS.labels(queue=queue_name).inc()
    return acquired


async def renew_job_lease(
    job_id: uuid.UUID,
    *,
    queue_name: str,
    owner: str,
    ttl_seconds: int,
    redis: Redis = redis_client,
) -> bool:
    script = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('EXPIRE', KEYS[1], ARGV[2])
    end
    return 0
    """
    result = await redis.eval(
        script,
        1,
        _lease_key(queue_name, job_id),
        owner,
        max(1, ttl_seconds),
    )
    return bool(result)


async def release_job_lease(
    job_id: uuid.UUID,
    *,
    queue_name: str,
    owner: str,
    redis: Redis = redis_client,
) -> bool:
    script = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    end
    return 0
    """
    result = await redis.eval(script, 1, _lease_key(queue_name, job_id), owner)
    released = bool(result)
    if released:
        ACTIVE_LEASES.labels(queue=queue_name).dec()
    return released


async def has_active_job_lease(
    job_id: uuid.UUID,
    *,
    queue_name: str,
    redis: Redis = redis_client,
) -> bool:
    return bool(await redis.exists(_lease_key(queue_name, job_id)))
