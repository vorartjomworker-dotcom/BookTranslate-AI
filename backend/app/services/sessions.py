from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_api_token, new_api_token
from app.core.config import settings
from app.models.app_user import AppUser
from app.models.user_session import UserSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_user_session(
    db: AsyncSession,
    *,
    user: AppUser,
    user_agent: str | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> tuple[UserSession, str, str]:
    now = _now()
    active = list(
        (
            await db.execute(
                select(UserSession)
                .where(
                    UserSession.user_id == user.id,
                    UserSession.revoked_at.is_(None),
                    UserSession.refresh_expires_at > now,
                )
                .order_by(UserSession.created_at.asc())
            )
        ).scalars().all()
    )
    overflow = max(0, len(active) - max(1, settings.session_max_active_per_user) + 1)
    for stale in active[:overflow]:
        stale.revoked_at = now

    access_token = new_api_token()
    refresh_token = new_api_token()
    session = UserSession(
        user_id=user.id,
        access_token_hash=hash_api_token(access_token),
        refresh_token_hash=hash_api_token(refresh_token),
        expires_at=now + timedelta(seconds=max(60, settings.session_access_ttl_seconds)),
        refresh_expires_at=now + timedelta(seconds=max(300, settings.session_refresh_ttl_seconds)),
        last_seen_at=now,
        user_agent=(user_agent or "")[:500] or None,
        ip_address=(ip_address or "")[:64] or None,
        metadata_json=metadata or {},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, access_token, refresh_token


async def refresh_user_session(
    db: AsyncSession,
    *,
    refresh_token: str,
) -> tuple[UserSession, AppUser, str, str]:
    now = _now()
    row = (
        await db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == hash_api_token(refresh_token),
                UserSession.revoked_at.is_(None),
                UserSession.refresh_expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError("Invalid or expired refresh token")
    user = await db.get(AppUser, row.user_id)
    if user is None or not user.is_active:
        raise ValueError("Inactive session user")

    access_token = new_api_token()
    next_refresh_token = new_api_token()
    row.access_token_hash = hash_api_token(access_token)
    row.refresh_token_hash = hash_api_token(next_refresh_token)
    row.expires_at = now + timedelta(seconds=max(60, settings.session_access_ttl_seconds))
    row.refresh_expires_at = now + timedelta(seconds=max(300, settings.session_refresh_ttl_seconds))
    row.last_seen_at = now
    await db.commit()
    await db.refresh(row)
    return row, user, access_token, next_refresh_token


async def revoke_session(db: AsyncSession, *, session: UserSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = _now()
        await db.commit()


async def revoke_all_user_sessions(db: AsyncSession, *, user_id) -> int:
    now = _now()
    rows = list(
        (
            await db.execute(
                select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.revoked_at.is_(None),
                )
            )
        ).scalars().all()
    )
    for row in rows:
        row.revoked_at = now
    if rows:
        await db.commit()
    return len(rows)
