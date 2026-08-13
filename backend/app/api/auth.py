import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, ROLES, get_current_actor, hash_api_token, new_api_token, require_roles
from app.core.config import settings
from app.db import get_db
from app.models.app_user import AppUser

router = APIRouter(tags=["auth"])


class BootstrapRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role: str = "viewer"


class UserRoleUpdate(BaseModel):
    role: str
    is_active: bool | None = None


def _user_out(user: AppUser, *, api_token: str | None = None) -> dict:
    data = {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "last_seen_at": user.last_seen_at,
        "created_at": user.created_at,
    }
    if api_token is not None:
        data["api_token"] = api_token
    return data


@router.post("/api/auth/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(
    payload: BootstrapRequest,
    x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    configured = settings.bootstrap_admin_token
    if not configured or not x_bootstrap_token or not secrets.compare_digest(configured, x_bootstrap_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")
    existing_count = (await db.execute(select(func.count(AppUser.id)))).scalar_one()
    if existing_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application users already exist")
    token = new_api_token()
    user = AppUser(
        email=str(payload.email).lower(),
        display_name=payload.display_name.strip(),
        role="admin",
        api_token_hash=hash_api_token(token),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user, api_token=token)


@router.get("/api/auth/me")
async def me(actor: AppUser | DevActor = Depends(get_current_actor)) -> dict:
    return {
        "id": str(actor.id) if actor.id else None,
        "email": actor.email,
        "display_name": actor.display_name,
        "role": actor.role,
        "is_active": actor.is_active,
        "development_identity": isinstance(actor, DevActor),
    }


@router.post("/api/admin/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of {sorted(ROLES)}")
    email = str(payload.email).lower()
    existing = (await db.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="User email already exists")
    token = new_api_token()
    user = AppUser(
        email=email,
        display_name=payload.display_name.strip(),
        role=payload.role,
        api_token_hash=hash_api_token(token),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user, api_token=token)


@router.get("/api/admin/users")
async def list_users(
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list((await db.execute(select(AppUser).order_by(AppUser.created_at))).scalars().all())
    return [_user_out(row) for row in rows]


@router.post("/api/admin/users/{user_id}/role")
async def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of {sorted(ROLES)}")
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@router.post("/api/admin/users/{user_id}/rotate-token")
async def rotate_user_token(
    user_id: uuid.UUID,
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    token = new_api_token()
    user.api_token_hash = hash_api_token(token)
    await db.commit()
    await db.refresh(user)
    return _user_out(user, api_token=token)
