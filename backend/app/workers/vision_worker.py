from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.observability import configure_tracing
from app.redis_client import redis_client
from app.services.job_queue import dequeue_job
from app.services.vision_jobs import process_vision_job, recover_vision_jobs
from app.storage.factory import create_storage
from app.vision.gateway import VisionGateway
from app.workers.lease import claimed_job_lease, new_worker_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booktranslate.vision_worker")


async def _recover() -> int:
    async with AsyncSessionLocal() as db:
        return await recover_vision_jobs(db, queue_name=settings.vision_queue_name, stale_after_seconds=settings.vision_job_recovery_age_seconds)


async def run_worker() -> None:
    configure_tracing(service_name="booktranslate-vision-worker")
    gateway = VisionGateway.from_settings(settings)
    storage = create_storage(settings)
    owner = new_worker_id("vision")
    logger.info("Vision worker %s recovered %s jobs", owner, await _recover())
    while True:
        job_id = await dequeue_job(queue_name=settings.vision_queue_name, timeout_seconds=settings.vision_worker_poll_seconds)
        if job_id is None:
            recovered = await _recover()
            if recovered:
                logger.info("Recovered %s stale/queued vision jobs", recovered)
            continue
        async with claimed_job_lease(job_id, queue_name=settings.vision_queue_name, owner=owner) as claimed:
            if not claimed:
                logger.info("Skipped vision job %s because another worker owns its lease", job_id)
                continue
            logger.info("Processing vision job %s", job_id)
            try:
                async with AsyncSessionLocal() as db:
                    job = await process_vision_job(db, gateway, job_id, storage=storage)
                    logger.info("Vision job %s finished with status %s", job_id, job.status)
            except Exception:
                logger.exception("Vision job %s crashed", job_id)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await redis_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
