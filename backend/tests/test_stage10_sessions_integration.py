import asyncio
import os

import pytest

from app.core.auth import authenticate_api_token, hash_api_token, new_api_token
from app.db import AsyncSessionLocal, engine
from app.models.app_user import AppUser
from app.services.sessions import create_user_session, refresh_user_session, revoke_session

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


async def _run() -> None:
    async with AsyncSessionLocal() as db:
        user = AppUser(
            email="stage10-session@example.test",
            display_name="Stage 10 Session",
            role="translator",
            api_token_hash=hash_api_token(new_api_token()),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        session, access, refresh = await create_user_session(
            db,
            user=user,
            user_agent="pytest",
            ip_address="127.0.0.1",
            metadata={"source": "test"},
        )
        assert (await authenticate_api_token(db, access)).id == user.id

        same_session, refreshed_user, access2, refresh2 = await refresh_user_session(db, refresh_token=refresh)
        assert same_session.id == session.id
        assert refreshed_user.id == user.id
        assert access2 != access
        assert refresh2 != refresh
        assert await authenticate_api_token(db, access) is None
        assert (await authenticate_api_token(db, access2)).id == user.id

        with pytest.raises(ValueError):
            await refresh_user_session(db, refresh_token=refresh)

        await revoke_session(db, session=same_session)
        assert await authenticate_api_token(db, access2) is None
        await db.delete(user)
        await db.commit()
    await engine.dispose()


def test_multi_session_access_and_refresh_rotation() -> None:
    asyncio.run(_run())
