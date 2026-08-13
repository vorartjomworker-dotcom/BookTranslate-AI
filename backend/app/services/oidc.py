from __future__ import annotations

import secrets
import time
import urllib.parse

import httpx
import jwt
from jwt import PyJWK
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ROLES, hash_api_token, new_api_token
from app.core.config import settings
from app.core.security import sign_payload, verify_payload
from app.models.app_user import AppUser
from app.models.user_session import UserSession
from app.services.sessions import create_user_session


def _require_oidc() -> None:
    required = [settings.oidc_issuer, settings.oidc_client_id, settings.oidc_client_secret]
    if not settings.oidc_enabled or not all(required):
        raise RuntimeError("OIDC is not fully configured")


async def discover_oidc(client: httpx.AsyncClient | None = None) -> dict:
    _require_oidc()
    url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
    if client is not None:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as owned:
        response = await owned.get(url)
        response.raise_for_status()
        return response.json()


async def build_authorization_url(*, return_to: str | None = None, client: httpx.AsyncClient | None = None) -> str:
    discovery = await discover_oidc(client)
    nonce = secrets.token_urlsafe(24)
    state = sign_payload(
        {
            "purpose": "oidc_state",
            "nonce": nonce,
            "return_to": return_to or settings.oidc_frontend_redirect_uri,
            "exp": int(time.time()) + 600,
        }
    )
    query = urllib.parse.urlencode(
        {
            "client_id": settings.oidc_client_id,
            "response_type": "code",
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": settings.oidc_scopes,
            "state": state,
            "nonce": nonce,
        }
    )
    return f"{discovery['authorization_endpoint']}?{query}"


async def _exchange_code(code: str, discovery: dict, client: httpx.AsyncClient) -> dict:
    response = await client.post(
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
        },
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    return response.json()


async def _validate_id_token(id_token: str, *, nonce: str, discovery: dict, client: httpx.AsyncClient) -> dict:
    jwks_response = await client.get(discovery["jwks_uri"])
    jwks_response.raise_for_status()
    jwks = jwks_response.json().get("keys") or []
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    alg = str(header.get("alg") or "")
    matching = next((item for item in jwks if item.get("kid") == kid), None)
    if matching is None:
        raise ValueError("OIDC signing key not found")
    key = PyJWK.from_dict(matching, algorithm=alg).key
    claims = jwt.decode(
        id_token,
        key=key,
        algorithms=[alg],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", "iat", "sub", "iss"]},
    )
    if claims.get("nonce") != nonce:
        raise ValueError("OIDC nonce mismatch")
    if claims.get("email_verified") is False:
        raise ValueError("OIDC email is explicitly unverified")
    return claims


async def complete_oidc_login(
    db: AsyncSession,
    *,
    code: str,
    state: str,
    client: httpx.AsyncClient | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[AppUser, str, str, UserSession, str]:
    state_payload = verify_payload(state, purpose="oidc_state")
    owned = client is None
    http = client or httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds)
    try:
        discovery = await discover_oidc(http)
        tokens = await _exchange_code(code, discovery, http)
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise ValueError("OIDC provider did not return id_token")
        claims = await _validate_id_token(id_token, nonce=str(state_payload["nonce"]), discovery=discovery, client=http)
        if not claims.get("email") and tokens.get("access_token") and discovery.get("userinfo_endpoint"):
            response = await http.get(
                discovery["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            response.raise_for_status()
            claims.update(response.json())
        if claims.get("email_verified") is False:
            raise ValueError("OIDC email is explicitly unverified")
    finally:
        if owned:
            await http.aclose()

    subject = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").lower().strip()
    if not subject or not email:
        raise ValueError("OIDC identity requires sub and email")
    display_name = str(claims.get("name") or claims.get("preferred_username") or email).strip()
    claimed_role = str(claims.get(settings.oidc_role_claim) or settings.oidc_default_role)
    role = claimed_role if claimed_role in ROLES else settings.oidc_default_role
    if role not in ROLES:
        role = "viewer"

    user = (
        await db.execute(
            select(AppUser).where(
                or_(
                    (AppUser.oidc_issuer == settings.oidc_issuer) & (AppUser.oidc_subject == subject),
                    AppUser.email == email,
                )
            )
        )
    ).scalars().first()
    if user is None:
        # Keep a distinct long-lived API token hash for service/API use, but do not
        # expose it during OIDC login. Browser sign-in uses expiring UserSession tokens.
        static_token = new_api_token()
        user = AppUser(
            email=email,
            display_name=display_name,
            role=role,
            api_token_hash=hash_api_token(static_token),
            oidc_issuer=settings.oidc_issuer,
            oidc_subject=subject,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        if user.oidc_subject and (user.oidc_subject != subject or user.oidc_issuer != settings.oidc_issuer):
            raise ValueError("Existing account is bound to another OIDC identity")
        user.display_name = display_name
        user.oidc_issuer = settings.oidc_issuer
        user.oidc_subject = subject
        if user.role == "viewer" and role != "viewer":
            user.role = role
        await db.commit()
        await db.refresh(user)

    session, access_token, refresh_token = await create_user_session(
        db,
        user=user,
        user_agent=user_agent,
        ip_address=ip_address,
        metadata={"source": "oidc", "issuer": settings.oidc_issuer},
    )
    return (
        user,
        access_token,
        refresh_token,
        session,
        str(state_payload.get("return_to") or settings.oidc_frontend_redirect_uri),
    )
