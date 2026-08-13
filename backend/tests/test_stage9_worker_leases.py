import asyncio
import os
import uuid

import pytest
from redis.asyncio import Redis

from app.core.config import settings
from app.services.job_queue import acquire_job_lease, has_active_job_lease, release_job_lease, renew_job_lease

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires Redis integration service")


async def _run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    job_id = uuid.uuid4()
    queue = "stage9-lease-test"
    try:
        assert await acquire_job_lease(job_id, queue_name=queue, owner="worker-a", ttl_seconds=30, redis=redis)
        assert await has_active_job_lease(job_id, queue_name=queue, redis=redis)
        assert not await acquire_job_lease(job_id, queue_name=queue, owner="worker-b", ttl_seconds=30, redis=redis)
        assert not await renew_job_lease(job_id, queue_name=queue, owner="worker-b", ttl_seconds=30, redis=redis)
        assert await renew_job_lease(job_id, queue_name=queue, owner="worker-a", ttl_seconds=30, redis=redis)
        assert not await release_job_lease(job_id, queue_name=queue, owner="worker-b", redis=redis)
        assert await release_job_lease(job_id, queue_name=queue, owner="worker-a", redis=redis)
        assert not await has_active_job_lease(job_id, queue_name=queue, redis=redis)
    finally:
        await redis.aclose()


def test_worker_lease_enforces_single_owner() -> None:
    asyncio.run(_run())
