from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from aimealplanner.core.config import Settings
from aimealplanner.core.logging import configure_logging
from aimealplanner.infrastructure.db.initialization import initialize_database
from aimealplanner.infrastructure.db.session import build_engine, build_session_factory
from aimealplanner.infrastructure.redis.client import build_redis, verify_redis
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


def build_runtime(settings: Settings | None = None) -> AppRuntime:
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings.log_level)

    engine = build_engine(resolved_settings.database_url)
    session_factory = build_session_factory(engine)
    redis = build_redis(resolved_settings.redis_url)
    bot = Bot(token=resolved_settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router())

    return AppRuntime(
        settings=resolved_settings,
        bot=bot,
        dispatcher=dispatcher,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
    )


async def run() -> None:
    runtime = build_runtime()
    try:
        await initialize_database(runtime.engine)
        await verify_redis(runtime.redis)
        logger.info("Starting bot in %s mode", runtime.settings.app_env)
        await runtime.dispatcher.start_polling(runtime.bot)
    finally:
        await runtime.bot.session.close()
        await runtime.redis.aclose()
        await runtime.engine.dispose()
