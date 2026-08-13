from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.redis_client import redis_client
from app.services.figure_rendering import process_figure_render_job, recover_figure_render_jobs
from app.services.job_queue import dequeue_job
from app.storage.factory import create_storage
from app.workers.lease import claimed_job_lease, new_worker_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booktranslate.figure_render_worker")


async def _recover() -> int:
    async with AsyncSessionLocal() as db:
        return await recover_figure_render_jobs(
            db,
            queue_name=settings.figure_render_queue_name,
            stale_after_seconds=settings.figure_render_job_recovery_age_seconds,
        )


async def run_worker() -> None:
    storage = create_storage(settings)
    owner = new_worker_id("figure-render")
    logger.info("Figure render worker %s recovered %s jobs", owner, await _recover())
    while True:
        job_id = await dequeue_job(
            queue_name=settings.figure_render_queue_name,
            timeout_seconds=settings.figure_render_worker_poll_seconds,
        )
        if job_id is None:
            recovered = await _recover()
            if recovered:
                logger.info("Recovered %s stale/queued figure render jobs", recovered)
            continue
        async with claimed_job_lease(job_id, queue_name=settings.figure_render_queue_name, owner=owner) as claimed:
            if not claimed:
                logger.info("Skipped figure render job %s because another worker owns its lease", job_id)
                continue
            logger.info("Processing figure render job %s", job_id)
            try:
                async with AsyncSessionLocal() as db:
                    job = await process_figure_render_job(db, storage, job_id)
                    logger.info("Figure render job %s finished with status %s", job_id, job.status)
            except Exception:
                logger.exception("Figure render job %s crashed", job_id)


async def _main() -> None:
    try:
        await run_worker()
    finally:
        await redis_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
