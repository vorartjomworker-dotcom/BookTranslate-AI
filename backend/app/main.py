from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.books import router as books_router
from app.api.upload import router as upload_router
from app.core.config import settings
from app.db import check_database
from app.redis_client import check_redis


app = FastAPI(title=settings.app_name, version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router)
app.include_router(upload_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}


@app.get("/liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health", response_model=None)
async def health():
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

    payload = {
        "status": "ok" if database_ok and redis_ok else "degraded",
        "database": database_ok,
        "redis": redis_ok,
    }

    if not (database_ok and redis_ok):
        return JSONResponse(status_code=503, content=payload)

    return payload
