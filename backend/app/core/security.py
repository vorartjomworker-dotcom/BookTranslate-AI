from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signing_secret() -> bytes:
    value = settings.auth_signing_secret
    if not value:
        raise RuntimeError("AUTH_SIGNING_SECRET must be configured for signed security tokens")
    return value.encode("utf-8")


def sign_payload(payload: dict[str, Any]) -> str:
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_signing_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def verify_payload(token: str, *, purpose: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed signed token") from exc
    expected = hmac.new(_signing_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    supplied = _b64decode(signature)
    if not hmac.compare_digest(expected, supplied):
        raise ValueError("Invalid signed token")
    payload = json.loads(_b64decode(encoded))
    if payload.get("purpose") != purpose:
        raise ValueError("Signed token purpose mismatch")
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("Signed token expired")
    return payload


def create_download_ticket(*, path: str, user_id: str | None, ttl_seconds: int | None = None) -> str:
    ttl = int(ttl_seconds or settings.download_ticket_ttl_seconds)
    return sign_payload(
        {
            "purpose": "download",
            "path": path,
            "sub": user_id,
            "exp": int(time.time()) + max(10, ttl),
        }
    )


def verify_download_ticket(token: str, *, path: str) -> dict[str, Any]:
    payload = verify_payload(token, purpose="download")
    if payload.get("path") != path:
        raise ValueError("Download ticket path mismatch")
    return payload
