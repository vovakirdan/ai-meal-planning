from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.presentation.telegram.handlers.onboarding import (
    build_onboarding_router,
)
from aimealplanner.presentation.telegram.handlers.planning import (
    build_planning_router,
)


def build_router(session_factory: async_sessionmaker[AsyncSession]) -> Router:
    router = Router(name="root")
    router.include_router(build_onboarding_router(session_factory))
    router.include_router(build_planning_router(session_factory))
    return router
