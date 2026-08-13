import secrets
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, ROLES, get_current_actor, hash_api_token, new_api_token, require_roles
from app.core.config import settings
from app.db import get_db
from app.models.app_user import AppUser
from app.services.oidc import build_authorization_url, complete_oidc_login

router = APIRouter(tags=["auth"])


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    role: str = "viewer"


class UserRoleUpdate(BaseModel):
    role: str
    is_active: bool | None = None


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="Valid email is required")
    return email


def _safe_return_to(value: str | None) -> str:
    configured = settings.oidc_frontend_redirect_uri
    if not value:
        return configured
    target = urllib.parse.urlparse(value)
    allowed = urllib.parse.urlparse(configured)
    if target.scheme != allowed.scheme or target.netloc != allowed.netloc:
        return configured
    return value


def _user_out(user: AppUser, *, api_token: str | None = None) -> dict:
    data = {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "oidc_issuer": user.oidc_issuer,
        "oidc_subject": user.oidc_subject,
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
        email=_normalize_email(payload.email),
        display_name=payload.display_name.strip(),
        role="admin",
        api_token_hash=hash_api_token(token),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(user, api_token=token)


@router.get("/api/auth/oidc/config")
async def oidc_config() -> dict:
    return {
        "enabled": settings.oidc_enabled,
        "issuer": settings.oidc_issuer if settings.oidc_enabled else None,
        "login_path": "/api/auth/oidc/login" if settings.oidc_enabled else None,
    }


@router.get("/api/auth/oidc/login")
async def oidc_login(return_to: str | None = Query(default=None)) -> RedirectResponse:
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC is not enabled")
    try:
        url = await build_authorization_url(return_to=_safe_return_to(return_to))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OIDC discovery failed: {exc}") from exc
    return RedirectResponse(url, status_code=302)


@router.get("/api/auth/oidc/callback")
async def oidc_callback(
    code: str | None = Query(default=None),
    state_value: str | None = Query(default=None, alias="state"),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=401, detail=f"OIDC login failed: {error}")
    if not code or not state_value:
        raise HTTPException(status_code=400, detail="OIDC callback requires code and state")
    try:
        user, token, return_to = await complete_oidc_login(db, code=code, state=state_value)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"OIDC callback validation failed: {exc}") from exc
    fragment = urllib.parse.urlencode({"token": token, "role": user.role, "user": user.display_name})
    return RedirectResponse(f"{_safe_return_to(return_to)}#{fragment}", status_code=302)


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
    email = _normalize_email(payload.email)
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
