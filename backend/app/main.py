from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.book_qa import router as book_qa_router
from app.api.books import router as books_router
from app.api.export import router as export_router
from app.api.figure_renders import router as figure_renders_router
from app.api.glossary import router as glossary_router
from app.api.jobs import router as jobs_router
from app.api.model_policies import router as model_policies_router
from app.api.ops import router as ops_router
from app.api.qa import router as qa_router
from app.api.reviewer import router as reviewer_router
from app.api.reviews import router as reviews_router
from app.api.translations import router as translations_router
from app.api.upload import router as upload_router
from app.api.vision import router as vision_router
from app.api.workbench import router as workbench_router
from app.core.config import settings
from app.db import check_database
from app.http_middleware import SecurityObservabilityMiddleware
from app.observability import configure_tracing
from app.redis_client import check_redis

app = FastAPI(title=settings.app_name, version="0.10.0")
configure_tracing(app=app)

app.add_middleware(SecurityObservabilityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(books_router)
app.include_router(upload_router)
app.include_router(export_router)
app.include_router(glossary_router)
app.include_router(translations_router)
app.include_router(jobs_router)
app.include_router(vision_router)
app.include_router(figure_renders_router)
app.include_router(qa_router)
app.include_router(reviews_router)
app.include_router(reviewer_router)
app.include_router(book_qa_router)
app.include_router(model_policies_router)
app.include_router(workbench_router)
app.include_router(ai_router)
app.include_router(ops_router)


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
    payload = {"status": "ok" if database_ok and redis_ok else "degraded", "database": database_ok, "redis": redis_ok}
    if not (database_ok and redis_ok):
        return JSONResponse(status_code=503, content=payload)
    return payload
