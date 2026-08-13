import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.provider_model_policy import ProviderModelPolicy

router = APIRouter(prefix="/api/ai/model-policies", tags=["model-policies"])


class PolicyUpsert(BaseModel):
    provider: str
    model: str
    enabled: bool = True
    priority: int = 100
    input_cost_per_million: Decimal = Decimal("0")
    output_cost_per_million: Decimal = Decimal("0")
    requests_per_minute: int | None = Field(default=None, gt=0)
    tokens_per_minute: int | None = Field(default=None, gt=0)
    max_concurrency: int | None = Field(default=None, gt=0)
    roles: list[str] = []


def _out(item: ProviderModelPolicy) -> dict:
    return {
        "id": str(item.id),
        "provider": item.provider,
        "model": item.model,
        "enabled": item.enabled,
        "priority": item.priority,
        "input_cost_per_million": str(item.input_cost_per_million),
        "output_cost_per_million": str(item.output_cost_per_million),
        "requests_per_minute": item.requests_per_minute,
        "tokens_per_minute": item.tokens_per_minute,
        "max_concurrency": item.max_concurrency,
        "roles": list((item.metadata_json or {}).get("roles", [])),
    }


@router.post("")
async def upsert_policy(payload: PolicyUpsert, db: AsyncSession = Depends(get_db)) -> dict:
    item = (
        await db.execute(
            select(ProviderModelPolicy).where(
                ProviderModelPolicy.provider == payload.provider,
                ProviderModelPolicy.model == payload.model,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = ProviderModelPolicy(provider=payload.provider, model=payload.model)
        db.add(item)
    item.enabled = payload.enabled
    item.priority = payload.priority
    item.input_cost_per_million = payload.input_cost_per_million
    item.output_cost_per_million = payload.output_cost_per_million
    item.requests_per_minute = payload.requests_per_minute
    item.tokens_per_minute = payload.tokens_per_minute
    item.max_concurrency = payload.max_concurrency
    item.metadata_json = {"roles": payload.roles}
    await db.commit()
    await db.refresh(item)
    return _out(item)


@router.get("")
async def list_policies(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = list(
        (
            await db.execute(
                select(ProviderModelPolicy).order_by(ProviderModelPolicy.priority, ProviderModelPolicy.provider, ProviderModelPolicy.model)
            )
        ).scalars().all()
    )
    return [_out(item) for item in rows]


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    item = await db.get(ProviderModelPolicy, policy_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model policy not found")
    await db.delete(item)
    await db.commit()
