from __future__ import annotations

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.auth import DevActor, authenticate_api_token
from app.core.config import settings
from app.core.security import verify_download_ticket
from app.db import AsyncSessionLocal
from app.models.audit_event import AuditEvent

REQUESTS = Counter("booktranslate_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("booktranslate_http_request_duration_seconds", "HTTP request latency", ["method", "route"])
IN_PROGRESS = Gauge("booktranslate_http_requests_in_progress", "In-progress HTTP requests")

_PUBLIC_API_PATHS = {
    "/api/auth/bootstrap",
    "/api/auth/oidc/config",
    "/api/auth/oidc/login",
    "/api/auth/oidc/callback",
}


def _bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization") or ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


def _is_export_path(path: str) -> bool:
    return path.startswith("/api/books/") and "/export/" in path


class SecurityObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        IN_PROGRESS.inc()
        actor = None
        try:
            if request.method != "OPTIONS" and request.url.path.startswith("/api/") and request.url.path not in _PUBLIC_API_PATHS:
                if not settings.auth_required:
                    actor = DevActor()
                    request.state.actor = actor
                else:
                    download_token = request.query_params.get("download_token")
                    if request.method == "GET" and download_token and _is_export_path(request.url.path):
                        try:
                            verify_download_ticket(download_token, path=request.url.path)
                            request.state.download_authorized = True
                        except Exception:
                            return JSONResponse(status_code=401, content={"detail": "Invalid or expired download ticket"})
                    else:
                        token = _bearer_token(request)
                        if not token:
                            return JSONResponse(status_code=401, content={"detail": "Bearer token required"})
                        async with AsyncSessionLocal() as db:
                            actor = await authenticate_api_token(db, token)
                        if actor is None:
                            return JSONResponse(status_code=401, content={"detail": "Invalid or inactive API token"})
                        request.state.actor = actor

            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            route = getattr(request.scope.get("route"), "path", request.url.path)
            REQUESTS.labels(request.method, route, str(response.status_code)).inc()
            LATENCY.labels(request.method, route).observe(time.perf_counter() - started)

            if settings.audit_enabled and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
                try:
                    current_actor = getattr(request.state, "actor", actor)
                    async with AsyncSessionLocal() as db:
                        db.add(
                            AuditEvent(
                                actor_user_id=getattr(current_actor, "id", None),
                                actor_email=getattr(current_actor, "email", None),
                                action=f"{request.method} {route}",
                                resource_type="api",
                                resource_id=request.url.path,
                                request_id=request_id,
                                metadata_json={"status_code": response.status_code},
                            )
                        )
                        await db.commit()
                except Exception:
                    pass
            return response
        finally:
            IN_PROGRESS.dec()
