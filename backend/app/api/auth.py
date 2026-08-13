import secrets
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, ROLES, get_current_actor, hash_api_token, new_api_token, require_roles
from app.core.config import settings
from app.db import get_db
from app.models.app_user import AppUser
from app.models.user_session import UserSession
from app.services.oidc import build_authorization_url, complete_oidc_login
from app.services.sessions import refresh_user_session, revoke_all_user_sessions, revoke_session

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


class SessionRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)


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
        "scim_external_id": user.scim_external_id,
        "scim_managed": user.scim_managed,
        "last_seen_at": user.last_seen_at,
        "created_at": user.created_at,
    }
    if api_token is not None:
        data["api_token"] = api_token
    return data


def _session_out(row: UserSession) -> dict:
    return {
        "id": str(row.id),
        "expires_at": row.expires_at,
        "refresh_expires_at": row.refresh_expires_at,
        "revoked_at": row.revoked_at,
        "last_seen_at": row.last_seen_at,
        "user_agent": row.user_agent,
        "ip_address": row.ip_address,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
    }


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
        "session_access_ttl_seconds": settings.session_access_ttl_seconds,
        "session_refresh_ttl_seconds": settings.session_refresh_ttl_seconds,
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
    request: Request,
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
        user, token, refresh_token, session, return_to = await complete_oidc_login(
            db,
            code=code,
            state=state_value,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"OIDC callback validation failed: {exc}") from exc
    fragment = urllib.parse.urlencode(
        {
            "token": token,
            "refresh_token": refresh_token,
            "expires_in": settings.session_access_ttl_seconds,
            "session_id": str(session.id),
            "role": user.role,
            "user": user.display_name,
        }
    )
    return RedirectResponse(f"{_safe_return_to(return_to)}#{fragment}", status_code=302)


@router.post("/api/auth/session/refresh")
async def refresh_session(payload: SessionRefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        session, user, access_token, refresh_token = await refresh_user_session(
            db,
            refresh_token=payload.refresh_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {
        "token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.session_access_ttl_seconds,
        "session": _session_out(session),
        "user": _user_out(user),
    }


@router.get("/api/auth/sessions")
async def list_sessions(
    actor: AppUser | DevActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if actor.id is None:
        return []
    rows = list(
        (
            await db.execute(
                select(UserSession)
                .where(UserSession.user_id == actor.id)
                .order_by(UserSession.created_at.desc())
            )
        ).scalars().all()
    )
    return [_session_out(row) for row in rows]


@router.delete("/api/auth/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    actor: AppUser | DevActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(UserSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if actor.role != "admin" and (actor.id is None or row.user_id != actor.id):
        raise HTTPException(status_code=403, detail="Cannot revoke another user's session")
    await revoke_session(db, session=row)
    return {"status": "revoked", "session_id": str(row.id)}


@router.post("/api/auth/sessions/revoke-all")
async def revoke_all_sessions(
    actor: AppUser | DevActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if actor.id is None:
        return {"revoked": 0}
    count = await revoke_all_user_sessions(db, user_id=actor.id)
    return {"revoked": count}


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
        if not payload.is_active:
            await revoke_all_user_sessions(db, user_id=user.id)
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
