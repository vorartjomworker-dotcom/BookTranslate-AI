from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)


async def check_database() -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True
