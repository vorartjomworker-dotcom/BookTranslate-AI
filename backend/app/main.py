from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import check_database
from app.redis_client import check_redis

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}


@app.get("/health")
async def health() -> dict[str, object]:
    database_ok = False
    redis_ok = False

    try:
        database_ok = await check_database()
    except Exception:
        database_ok = False

    try:
        redis_ok = await check_redis()
    except Exception:
        redis_ok = False

    status = "ok" if database_ok and redis_ok else "degraded"
    return {
        "status": status,
        "database": database_ok,
        "redis": redis_ok,
    }
