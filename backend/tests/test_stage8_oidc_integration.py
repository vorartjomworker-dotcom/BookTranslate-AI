import asyncio
import json
import os
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.auth import authenticate_api_token
from app.core.config import settings
from app.core.security import sign_payload
from app.db import AsyncSessionLocal, engine
from app.models.app_user import AppUser
from app.models.user_session import UserSession
from app.services.oidc import complete_oidc_login

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="requires migrated PostgreSQL")


async def _run() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "stage8-key", "alg": "RS256", "use": "sig"})
    nonce = "stage8-nonce"
    now = int(time.time())
    id_token = jwt.encode(
        {
            "iss": "https://idp.test",
            "sub": "user-123",
            "aud": "booktranslate-client",
            "iat": now,
            "exp": now + 600,
            "nonce": nonce,
            "email": "oidc-stage8@example.test",
            "name": "OIDC Reviewer",
            "booktranslate_role": "reviewer",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "stage8-key"},
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": "https://idp.test",
                "authorization_endpoint": "https://idp.test/authorize",
                "token_endpoint": "https://idp.test/token",
                "jwks_uri": "https://idp.test/jwks",
            })
        if request.url.path == "/token" and request.method == "POST":
            return httpx.Response(200, json={"id_token": id_token, "access_token": "access"})
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        return httpx.Response(404)

    previous = {
        "oidc_enabled": settings.oidc_enabled,
        "oidc_issuer": settings.oidc_issuer,
        "oidc_client_id": settings.oidc_client_id,
        "oidc_client_secret": settings.oidc_client_secret,
        "oidc_role_claim": settings.oidc_role_claim,
        "oidc_default_role": settings.oidc_default_role,
        "auth_signing_secret": settings.auth_signing_secret,
    }
    settings.oidc_enabled = True
    settings.oidc_issuer = "https://idp.test"
    settings.oidc_client_id = "booktranslate-client"
    settings.oidc_client_secret = "client-secret"
    settings.oidc_role_claim = "booktranslate_role"
    settings.oidc_default_role = "viewer"
    settings.auth_signing_secret = "oidc-state-secret"

    state = sign_payload({"purpose": "oidc_state", "nonce": nonce, "return_to": "http://localhost:3000/auth/callback", "exp": now + 600})
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://idp.test") as client:
            async with AsyncSessionLocal() as db:
                user, access_token, refresh_token, session, return_to = await complete_oidc_login(
                    db,
                    code="auth-code",
                    state=state,
                    client=client,
                    user_agent="stage10-test",
                    ip_address="127.0.0.1",
                )
                assert user.email == "oidc-stage8@example.test"
                assert user.role == "reviewer"
                assert user.oidc_subject == "user-123"
                assert return_to == "http://localhost:3000/auth/callback"
                assert refresh_token
                assert session.user_agent == "stage10-test"
                authenticated = await authenticate_api_token(db, access_token)
                assert authenticated is not None and authenticated.id == user.id
                stored_session = await db.get(UserSession, session.id)
                assert stored_session is not None and stored_session.revoked_at is None
                user_id = user.id

        async with AsyncSessionLocal() as db:
            stored = await db.get(AppUser, user_id)
            if stored is not None:
                await db.delete(stored)
                await db.commit()
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)
        await engine.dispose()


def test_oidc_login_validates_nonce_and_provisions_local_user() -> None:
    asyncio.run(_run())
