from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from aimealplanner.infrastructure.db import models  # noqa: F401
from aimealplanner.infrastructure.db.base import Base


async def initialize_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
