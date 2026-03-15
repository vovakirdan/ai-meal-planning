from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.presentation.telegram.handlers.onboarding import (
    build_onboarding_router,
)
from aimealplanner.presentation.telegram.handlers.plan_browser import (
    build_plan_browser_router,
)
from aimealplanner.presentation.telegram.handlers.planning import (
    build_planning_router,
)


def build_router(
    session_factory: async_sessionmaker[AsyncSession],
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
) -> Router:
    router = Router(name="root")
    router.include_router(build_onboarding_router(session_factory))
    router.include_router(build_planning_router(session_factory, weekly_plan_generator))
    router.include_router(build_plan_browser_router(session_factory))
    return router
