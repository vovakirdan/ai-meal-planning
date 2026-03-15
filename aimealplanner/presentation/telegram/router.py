from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.presentation.telegram.handlers.onboarding import (
    build_onboarding_router,
)


def build_router(session_factory: async_sessionmaker[AsyncSession]) -> Router:
    router = Router(name="root")
    router.include_router(build_onboarding_router(session_factory))
    return router
