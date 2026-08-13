import asyncio
import os

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.book import Book

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


async def _run() -> None:
    previous = {
        "auth_required": settings.auth_required,
        "metrics_token": settings.metrics_token,
        "audit_enabled": settings.audit_enabled,
    }
    settings.auth_required = False
    settings.metrics_token = "metrics-secret"
    settings.audit_enabled = True
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get("/metrics")
            assert denied.status_code == 403
            allowed = await client.get("/metrics", headers={"X-Metrics-Token": "metrics-secret"})
            assert allowed.status_code == 200
            assert "booktranslate_http_requests_total" in allowed.text
            bearer = await client.get("/metrics", headers={"Authorization": "Bearer metrics-secret"})
            assert bearer.status_code == 200
            assert "booktranslate_http_requests_total" in bearer.text

            created = await client.post(
                "/api/books",
                json={"title": "Audit Stage 8", "source_language": "en", "target_language": "ru"},
            )
            assert created.status_code in {200, 201}
            book_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            audit = (
                await db.execute(
                    select(AuditEvent).where(AuditEvent.action == "POST /api/books").order_by(AuditEvent.created_at.desc())
                )
            ).scalars().first()
            assert audit is not None
            assert audit.request_id
            book = await db.get(Book, book_id)
            if book is not None:
                await db.delete(book)
            await db.execute(delete(AuditEvent).where(AuditEvent.id == audit.id))
            await db.commit()
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)
        await engine.dispose()


def test_metrics_token_and_mutation_audit() -> None:
    asyncio.run(_run())
