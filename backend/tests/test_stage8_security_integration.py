import asyncio
import os

import httpx
import pytest

from app.core.auth import hash_api_token
from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.main import app
from app.models.app_user import AppUser
from app.models.book import Book

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


async def _run() -> None:
    token = "stage8-secret-user-token"
    async with AsyncSessionLocal() as db:
        user = AppUser(
            email="stage8-security@example.test",
            display_name="Stage 8 Security",
            role="admin",
            api_token_hash=hash_api_token(token),
            is_active=True,
        )
        book = Book(title="Protected Book", source_language="en", target_language="ru", status="created")
        db.add_all([user, book])
        await db.commit()
        await db.refresh(book)
        book_id = book.id

    old_auth = settings.auth_required
    old_secret = settings.auth_signing_secret
    old_audit = settings.audit_enabled
    settings.auth_required = True
    settings.auth_signing_secret = "stage8-signing-secret"
    settings.audit_enabled = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.get("/api/books")
            assert unauthenticated.status_code == 401

            headers = {"Authorization": f"Bearer {token}"}
            authenticated = await client.get("/api/books", headers=headers)
            assert authenticated.status_code == 200

            ticket_response = await client.post(
                f"/api/books/{book_id}/export-ticket",
                headers=headers,
                json={"format": "docx"},
            )
            assert ticket_response.status_code == 200
            signed_url = ticket_response.json()["url"]
            assert "download_token=" in signed_url

            protected_download = await client.get(signed_url)
            assert protected_download.status_code == 200
            assert protected_download.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

            bad_download = await client.get(f"/api/books/{book_id}/export/docx?download_token=bad")
            assert bad_download.status_code == 401
    finally:
        settings.auth_required = old_auth
        settings.auth_signing_secret = old_secret
        settings.audit_enabled = old_audit
        async with AsyncSessionLocal() as db:
            user = await db.get(AppUser, user.id)
            book = await db.get(Book, book_id)
            if book is not None:
                await db.delete(book)
            if user is not None:
                await db.delete(user)
            await db.commit()
        await engine.dispose()


def test_full_api_perimeter_and_signed_downloads() -> None:
    asyncio.run(_run())
