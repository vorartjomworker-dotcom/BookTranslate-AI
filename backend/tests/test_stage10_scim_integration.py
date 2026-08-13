import asyncio
import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.main import app
from app.models.app_user import AppUser
from app.models.audit_event import AuditEvent

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


async def _run() -> None:
    previous = {
        "scim_enabled": settings.scim_enabled,
        "scim_bearer_token": settings.scim_bearer_token,
        "scim_default_role": settings.scim_default_role,
        "scim_role_group_prefix": settings.scim_role_group_prefix,
    }
    settings.scim_enabled = True
    settings.scim_bearer_token = "stage10-scim-secret"
    settings.scim_default_role = "viewer"
    settings.scim_role_group_prefix = "BookTranslate-"
    headers = {"Authorization": "Bearer stage10-scim-secret"}
    transport = httpx.ASGITransport(app=app)
    user_id: str | None = None
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            config = await client.get("/scim/v2/ServiceProviderConfig", headers=headers)
            assert config.status_code == 200
            assert config.json()["patch"]["supported"] is True

            created = await client.post(
                "/scim/v2/Users",
                headers=headers,
                json={
                    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                    "externalId": "idp-stage10-1",
                    "userName": "scim-stage10@example.test",
                    "displayName": "SCIM Translator",
                    "active": True,
                    "roles": [{"value": "translator"}],
                },
            )
            assert created.status_code == 201, created.text
            payload = created.json()
            user_id = payload["id"]
            assert payload["roles"][0]["value"] == "translator"

            filtered = await client.get(
                '/scim/v2/Users?filter=userName%20eq%20%22scim-stage10%40example.test%22',
                headers=headers,
            )
            assert filtered.status_code == 200
            assert filtered.json()["totalResults"] == 1

            groups = await client.get("/scim/v2/Groups", headers=headers)
            assert groups.status_code == 200
            translator_group = next(
                item for item in groups.json()["Resources"] if item["displayName"] == "BookTranslate-translator"
            )
            assert any(member["value"] == user_id for member in translator_group["members"])

            patched = await client.patch(
                f"/scim/v2/Users/{user_id}",
                headers=headers,
                json={
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [{"op": "Replace", "path": "roles", "value": [{"value": "reviewer"}]}],
                },
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["roles"][0]["value"] == "reviewer"

            deleted = await client.delete(f"/scim/v2/Users/{user_id}", headers=headers)
            assert deleted.status_code == 204

        assert user_id is not None
        async with AsyncSessionLocal() as db:
            stored = await db.get(AppUser, uuid.UUID(user_id))
            assert stored is not None
            assert stored.scim_managed is True
            assert stored.scim_external_id == "idp-stage10-1"
            assert stored.is_active is False

            audit_rows = list(
                (
                    await db.execute(
                        select(AuditEvent).where(
                            AuditEvent.resource_type == "scim",
                            AuditEvent.resource_id.like("/scim/v2/Users%"),
                        )
                    )
                ).scalars().all()
            )
            assert any(row.action == "POST /scim/v2/Users" for row in audit_rows)
            assert any(row.action == "PATCH /scim/v2/Users/{user_id}" for row in audit_rows)
            assert any(row.action == "DELETE /scim/v2/Users/{user_id}" for row in audit_rows)

            await db.execute(
                delete(AuditEvent).where(
                    AuditEvent.resource_type == "scim",
                    AuditEvent.resource_id.like("/scim/v2/Users%"),
                )
            )
            await db.delete(stored)
            await db.commit()
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)
        await engine.dispose()


def test_scim_user_lifecycle_and_role_groups() -> None:
    asyncio.run(_run())
