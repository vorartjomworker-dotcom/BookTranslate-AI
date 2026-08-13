from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models.app_user import AppUser

ROLES = {"admin", "reviewer", "translator", "viewer"}
ROLE_LEVEL = {"viewer": 0, "translator": 1, "reviewer": 2, "admin": 3}
_bearer = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class DevActor:
    id: uuid.UUID | None = None
    email: str = "dev@local"
    display_name: str = "Local developer"
    role: str = "admin"
    is_active: bool = True


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_api_token() -> str:
    return secrets.token_urlsafe(40)


async def authenticate_api_token(db: AsyncSession, token: str) -> AppUser | None:
    token_hash = hash_api_token(token)
    actor = (
        await db.execute(
            select(AppUser).where(AppUser.api_token_hash == token_hash, AppUser.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if actor is not None:
        actor.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
    return actor


async def get_current_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AppUser | DevActor:
    state_actor = getattr(request.state, "actor", None)
    if state_actor is not None:
        return state_actor
    if not settings.auth_required and credentials is None:
        return DevActor()
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    actor = await authenticate_api_token(db, credentials.credentials)
    if actor is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API token")
    return actor


def require_roles(*roles: str) -> Callable:
    invalid = set(roles) - ROLES
    if invalid:
        raise ValueError(f"Unknown roles: {sorted(invalid)}")

    async def dependency(actor: AppUser | DevActor = Depends(get_current_actor)) -> AppUser | DevActor:
        if actor.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return actor

    return dependency


def require_min_role(role: str) -> Callable:
    if role not in ROLE_LEVEL:
        raise ValueError(f"Unknown role: {role}")

    async def dependency(actor: AppUser | DevActor = Depends(get_current_actor)) -> AppUser | DevActor:
        if ROLE_LEVEL.get(actor.role, -1) < ROLE_LEVEL[role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return actor

    return dependency
