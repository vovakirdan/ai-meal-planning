from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.recipes import SpoonacularRecipeHintProvider
from aimealplanner.presentation.telegram.handlers.onboarding import (
    build_onboarding_router,
)
from aimealplanner.presentation.telegram.handlers.plan_browser import (
    build_plan_browser_router,
)
from aimealplanner.presentation.telegram.handlers.planning import (
    build_planning_router,
)
from aimealplanner.presentation.telegram.handlers.review import (
    build_review_router,
)


def build_router(
    session_factory: async_sessionmaker[AsyncSession],
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
    *,
    recipe_hint_provider: SpoonacularRecipeHintProvider | None,
) -> Router:
    router = Router(name="root")
    router.include_router(build_onboarding_router(session_factory))
    router.include_router(
        build_planning_router(
            session_factory,
            weekly_plan_generator,
            recipe_hint_provider=recipe_hint_provider,
        ),
    )
    router.include_router(
        build_plan_browser_router(
            session_factory,
            weekly_plan_generator=weekly_plan_generator,
            recipe_hint_provider=recipe_hint_provider,
        ),
    )
    router.include_router(
        build_review_router(
            session_factory,
            weekly_plan_generator=weekly_plan_generator,
        ),
    )
    return router
