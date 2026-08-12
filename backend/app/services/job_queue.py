from __future__ import annotations

import uuid

from redis.asyncio import Redis

from app.redis_client import redis_client

_QUEUE_PREFIX = "booktranslate:queue"
_ENQUEUED_PREFIX = "booktranslate:queued"


def _queue_key(queue_name: str) -> str:
    return f"{_QUEUE_PREFIX}:{queue_name}"


def _enqueued_key(queue_name: str) -> str:
    return f"{_ENQUEUED_PREFIX}:{queue_name}"


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
