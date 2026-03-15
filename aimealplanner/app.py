from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from aimealplanner.application.analytics import AnalyticsTracker
from aimealplanner.application.planning.feedback_service import DishReviewService
from aimealplanner.application.planning.service import PlanningService
from aimealplanner.application.reminders import ReminderScheduler, ReminderService
from aimealplanner.core.config import Settings
from aimealplanner.core.logging import configure_logging
from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.analytics import build_analytics_tracker
from aimealplanner.infrastructure.db.initialization import verify_database_connection
from aimealplanner.infrastructure.db.repositories import (
    build_planning_repositories,
    build_reminder_repository,
)
from aimealplanner.infrastructure.db.session import build_engine, build_session_factory
from aimealplanner.infrastructure.monitoring import SentryMonitor, build_sentry_monitor
from aimealplanner.infrastructure.recipes import SpoonacularRecipeHintProvider
from aimealplanner.infrastructure.redis.client import build_redis, verify_redis
from aimealplanner.presentation.telegram.commands import build_public_bot_commands
from aimealplanner.presentation.telegram.middlewares import SentryContextMiddleware
from aimealplanner.presentation.telegram.router import build_router

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppRuntime:
    settings: Settings
    bot: Bot
    dispatcher: Dispatcher
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    weekly_plan_generator: OpenAIWeeklyPlanGenerator
    recipe_hint_provider: SpoonacularRecipeHintProvider | None
    sentry: SentryMonitor
    analytics: AnalyticsTracker
    reminder_scheduler: ReminderScheduler


def build_runtime(settings: Settings | None = None) -> AppRuntime:
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings.log_level)
    sentry = build_sentry_monitor(resolved_settings)

    engine = build_engine(resolved_settings.database_url)
    session_factory = build_session_factory(engine)
    redis = build_redis(resolved_settings.redis_url)
    weekly_plan_generator = OpenAIWeeklyPlanGenerator.from_settings(resolved_settings)
    recipe_hint_provider = SpoonacularRecipeHintProvider.from_settings(resolved_settings)
    analytics = build_analytics_tracker(resolved_settings)
    bot = Bot(token=resolved_settings.bot_token)
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher.update.outer_middleware(SentryContextMiddleware())
    dispatcher.include_router(
        build_router(
            session_factory,
            weekly_plan_generator,
            recipe_hint_provider=recipe_hint_provider,
            analytics=analytics,
        ),
    )
    reminder_service = ReminderService(
        session_factory=session_factory,
        repositories_factory=build_reminder_repository,
        review_service=DishReviewService(
            session_factory,
            build_planning_repositories,
            comment_client=weekly_plan_generator,
        ),
        planning_service=PlanningService(
            session_factory,
            build_planning_repositories,
        ),
    )
    reminder_scheduler = ReminderScheduler(
        bot=bot,
        redis=redis,
        reminder_service=reminder_service,
        analytics=analytics,
    )

    return AppRuntime(
        settings=resolved_settings,
        bot=bot,
        dispatcher=dispatcher,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        weekly_plan_generator=weekly_plan_generator,
        recipe_hint_provider=recipe_hint_provider,
        sentry=sentry,
        analytics=analytics,
        reminder_scheduler=reminder_scheduler,
    )


async def run() -> None:
    runtime = build_runtime()
    reminder_task: asyncio.Task[None] | None = None
    try:
        await verify_database_connection(runtime.engine)
        await verify_redis(runtime.redis)
        await runtime.bot.set_my_commands(build_public_bot_commands())
        reminder_task = asyncio.create_task(runtime.reminder_scheduler.run_forever())
        logger.info("Starting bot in %s mode", runtime.settings.app_env)
        await runtime.dispatcher.start_polling(runtime.bot)
    finally:
        if reminder_task is not None:
            reminder_task.cancel()
            with suppress(asyncio.CancelledError):
                await reminder_task
        await runtime.bot.session.close()
        await runtime.redis.aclose()
        if runtime.recipe_hint_provider is not None:
            await runtime.recipe_hint_provider.close()
        await runtime.sentry.aclose()
        await runtime.analytics.aclose()
        await runtime.weekly_plan_generator.close()
        await runtime.engine.dispose()
