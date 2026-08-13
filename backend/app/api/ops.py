import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DevActor, require_roles
from app.core.config import settings
from app.db import check_database, get_db
from app.models.app_user import AppUser
from app.models.audit_event import AuditEvent
from app.models.translation_job import TranslationJob
from app.models.vision_job import VisionJob
from app.redis_client import check_redis

router = APIRouter(tags=["operations"])


@router.get("/metrics", include_in_schema=False)
async def metrics(x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token")) -> Response:
    configured = settings.metrics_token
    if configured:
        if not x_metrics_token or not secrets.compare_digest(configured, x_metrics_token):
            raise HTTPException(status_code=403, detail="Invalid metrics token")
    elif settings.auth_required:
        raise HTTPException(status_code=503, detail="METRICS_TOKEN must be configured when AUTH_REQUIRED=true")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/ops/status")
async def operations_status(
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    database_ok = await check_database()
    redis_ok = await check_redis()
    translation_jobs = (
        await db.execute(select(func.count(TranslationJob.id)).where(TranslationJob.status.in_(["queued", "running"])))
    ).scalar_one()
    vision_jobs = (
        await db.execute(select(func.count(VisionJob.id)).where(VisionJob.status.in_(["queued", "running"])))
    ).scalar_one()
    return {
        "status": "ok" if database_ok and redis_ok else "degraded",
        "database": database_ok,
        "redis": redis_ok,
        "active_translation_jobs": int(translation_jobs or 0),
        "active_vision_jobs": int(vision_jobs or 0),
    }


@router.get("/api/admin/audit-events")
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    _actor: AppUser | DevActor = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list((await db.execute(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit))).scalars().all())
    return [
        {
            "id": str(row.id),
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "actor_email": row.actor_email,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "request_id": row.request_id,
            "metadata": row.metadata_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]
