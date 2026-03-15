from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from aimealplanner import __version__
from aimealplanner.core.config import AppEnv, Settings

logger = logging.getLogger(__name__)

_SENTRY_FLUSH_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class SentryMonitor:
    enabled: bool

    async def aclose(self) -> None:
        if not self.enabled:
            return
        await asyncio.to_thread(sentry_sdk.flush, _SENTRY_FLUSH_TIMEOUT_SECONDS)


def build_sentry_monitor(settings: Settings) -> SentryMonitor:
    if settings.sentry_dsn is None:
        return SentryMonitor(enabled=False)

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=f"aimealplanner@{__version__}",
        send_default_pii=False,
        traces_sample_rate=_resolve_traces_sample_rate(settings.app_env),
        enable_logs=True,
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    logger.info("Sentry monitoring is enabled for environment %s", settings.app_env)
    return SentryMonitor(enabled=True)


def _resolve_traces_sample_rate(app_env: AppEnv) -> float:
    sample_rates = {
        "development": 1.0,
        "test": 0.0,
        "production": 0.2,
    }
    return sample_rates[app_env]
