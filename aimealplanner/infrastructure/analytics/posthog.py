from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from posthog import Posthog

from aimealplanner.application.analytics import (
    AnalyticsProperties,
    AnalyticsTracker,
    NullAnalyticsTracker,
)
from aimealplanner.core.config import Settings

logger = logging.getLogger(__name__)

_POSTHOG_TIMEOUT_SECONDS = 5
_POSTHOG_FLUSH_AT = 20
_POSTHOG_FLUSH_INTERVAL_SECONDS = 0.5

type PosthogClientFactory = Callable[..., Any]


def build_analytics_tracker(
    settings: Settings,
    *,
    client_factory: PosthogClientFactory = Posthog,
) -> AnalyticsTracker:
    if settings.posthog_api_key is None:
        return NullAnalyticsTracker()

    client = client_factory(
        project_api_key=settings.posthog_api_key,
        host=settings.posthog_host,
        debug=False,
        disable_geoip=True,
        flush_at=_POSTHOG_FLUSH_AT,
        flush_interval=_POSTHOG_FLUSH_INTERVAL_SECONDS,
        gzip=True,
        max_retries=3,
        sync_mode=False,
        timeout=_POSTHOG_TIMEOUT_SECONDS,
        on_error=_log_posthog_error,
    )
    return PosthogAnalyticsTracker(client=client, app_env=settings.app_env)


class PosthogAnalyticsTracker:
    def __init__(self, *, client: Any, app_env: str) -> None:
        self._client = client
        self._app_env = app_env

    def identify(
        self,
        *,
        telegram_user_id: int,
        properties: AnalyticsProperties | None = None,
    ) -> None:
        resolved_properties = {
            "source": "telegram",
            "app_env": self._app_env,
            "telegram_user_id": telegram_user_id,
            **dict(properties or {}),
        }
        try:
            self._client.set(
                distinct_id=_telegram_distinct_id(telegram_user_id),
                properties=resolved_properties,
            )
        except Exception:
            logger.exception(
                "failed to identify telegram user %s in PostHog",
                telegram_user_id,
            )

    def capture(
        self,
        *,
        telegram_user_id: int,
        event: str,
        properties: AnalyticsProperties | None = None,
    ) -> None:
        resolved_properties = {
            "source": "telegram",
            "app_env": self._app_env,
            **dict(properties or {}),
        }
        try:
            self._client.capture(
                event,
                distinct_id=_telegram_distinct_id(telegram_user_id),
                properties=resolved_properties,
            )
        except Exception:
            logger.exception(
                "failed to capture PostHog event %s for telegram user %s",
                event,
                telegram_user_id,
            )

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.shutdown)


def _telegram_distinct_id(telegram_user_id: int) -> str:
    return f"telegram:{telegram_user_id}"


def _log_posthog_error(error: Exception) -> None:
    logger.warning("posthog client error: %s", error)
