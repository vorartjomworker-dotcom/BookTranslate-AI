from __future__ import annotations

import asyncio
import logging

from app.ai.gateway import ModelGateway
from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.observability import configure_tracing
from app.redis_client import redis_client
from app.services.job_queue import dequeue_job
from app.services.translation_jobs import process_job, recover_jobs
from app.workers.lease import claimed_job_lease, new_worker_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booktranslate.translation_worker")


async def _recover() -> int:
    async with AsyncSessionLocal() as db:
        return await recover_jobs(db, queue_name=settings.translation_queue_name, stale_after_seconds=settings.translation_job_recovery_age_seconds)


async def run_worker() -> None:
    configure_tracing(service_name="booktranslate-translation-worker")
    gateway = ModelGateway.from_settings(settings)
    owner = new_worker_id("translation")
    logger.info("Translation worker %s recovered %s jobs", owner, await _recover())
    while True:
        job_id = await dequeue_job(queue_name=settings.translation_queue_name, timeout_seconds=settings.translation_worker_poll_seconds)
        if job_id is None:
            recovered = await _recover()
            if recovered:
                logger.info("Recovered %s stale/queued translation jobs", recovered)
            continue
        async with claimed_job_lease(job_id, queue_name=settings.translation_queue_name, owner=owner) as claimed:
            if not claimed:
                logger.info("Skipped translation job %s because another worker owns its lease", job_id)
                continue
            logger.info("Processing translation job %s", job_id)
            try:
                async with AsyncSessionLocal() as db:
                    job = await process_job(db, gateway, job_id)
                    logger.info("Translation job %s finished with status %s", job_id, job.status)
            except Exception:
                logger.exception("Translation job %s crashed", job_id)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await redis_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
