from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import uuid
from contextlib import asynccontextmanager

from app.core.config import settings
from app.services.job_queue import acquire_job_lease, release_job_lease, renew_job_lease

logger = logging.getLogger("booktranslate.worker_lease")


def new_worker_id(kind: str) -> str:
    return f"{kind}:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:10]}"


@asynccontextmanager
async def claimed_job_lease(job_id: uuid.UUID, *, queue_name: str, owner: str):
    acquired = await acquire_job_lease(
        job_id,
        queue_name=queue_name,
        owner=owner,
        ttl_seconds=settings.worker_lease_seconds,
    )
    if not acquired:
        yield False
        return

    stop = asyncio.Event()

    async def heartbeat() -> None:
        interval = max(1, min(settings.worker_lease_renew_seconds, settings.worker_lease_seconds // 2 or 1))
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass
            try:
                renewed = await renew_job_lease(
                    job_id,
                    queue_name=queue_name,
                    owner=owner,
                    ttl_seconds=settings.worker_lease_seconds,
                )
                if not renewed:
                    logger.error("Lost %s lease for job %s owned by %s", queue_name, job_id, owner)
                    break
            except Exception:
                logger.exception("Could not renew %s lease for job %s", queue_name, job_id)

    task = asyncio.create_task(heartbeat(), name=f"lease-heartbeat:{queue_name}:{job_id}")
    try:
        yield True
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        try:
            await release_job_lease(job_id, queue_name=queue_name, owner=owner)
        except Exception:
            logger.exception("Could not release %s lease for job %s", queue_name, job_id)
