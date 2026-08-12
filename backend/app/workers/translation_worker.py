from __future__ import annotations

import asyncio
import logging

from app.ai.gateway import ModelGateway
from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.redis_client import redis_client
from app.services.job_queue import dequeue_job
from app.services.translation_jobs import process_job, recover_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booktranslate.translation_worker")


async def run_worker() -> None:
    gateway = ModelGateway.from_settings(settings)
    async with AsyncSessionLocal() as db:
        recovered = await recover_jobs(
            db,
            queue_name=settings.translation_queue_name,
            stale_after_seconds=settings.translation_job_recovery_age_seconds,
        )
        logger.info("Recovered %s translation jobs", recovered)

    while True:
        job_id = await dequeue_job(
            queue_name=settings.translation_queue_name,
            timeout_seconds=settings.translation_worker_poll_seconds,
        )
        if job_id is None:
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
