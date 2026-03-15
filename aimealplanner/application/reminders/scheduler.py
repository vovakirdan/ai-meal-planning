from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram.client.bot import Bot
from redis.asyncio import Redis

from aimealplanner.application.analytics import AnalyticsTracker
from aimealplanner.application.reminders.service import ReminderService

logger = logging.getLogger(__name__)
_DEFAULT_DEDUPE_TTL_SECONDS = 7 * 24 * 60 * 60


class ReminderScheduler:
    def __init__(
        self,
        *,
        bot: Bot,
        redis: Redis,
        reminder_service: ReminderService,
        analytics: AnalyticsTracker,
        interval_seconds: int = 30,
    ) -> None:
        self._bot = bot
        self._redis = redis
        self._reminder_service = reminder_service
        self._analytics = analytics
        self._interval_seconds = interval_seconds

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("reminder scheduler iteration failed")
            await asyncio.sleep(self._interval_seconds)

    async def run_once(self) -> None:
        dispatches = await self._reminder_service.collect_due_dispatches(datetime.now(tz=UTC))
        for dispatch in dispatches:
            acquired = await self._redis.set(
                dispatch.dedupe_key,
                "1",
                ex=_DEFAULT_DEDUPE_TTL_SECONDS,
                nx=True,
            )
            if not acquired:
                continue
            try:
                await self._bot.send_message(
                    dispatch.telegram_user_id,
                    dispatch.text,
                )
                self._analytics.capture(
                    telegram_user_id=dispatch.telegram_user_id,
                    event="reminder_sent",
                    properties={"kind": dispatch.kind},
                )
            except Exception:
                await self._redis.delete(dispatch.dedupe_key)
                raise
