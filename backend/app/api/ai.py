from fastapi import APIRouter

from app.ai.gateway import ModelGateway
from app.core.config import settings


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/providers")
async def list_ai_providers() -> dict[str, list[str]]:
    gateway = ModelGateway.from_settings(settings)
    return {"configured": gateway.available_providers}
