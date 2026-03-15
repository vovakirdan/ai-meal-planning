from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from aimealplanner.core.config import Settings
from aimealplanner.infrastructure.monitoring.sentry import (
    SentryMonitor,
    build_sentry_monitor,
)


def _build_settings(*, sentry_dsn: str | None, app_env: str = "development") -> Settings:
    return Settings(
        bot_token="123456:realistic-token",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        sentry_dsn=sentry_dsn,
        ai_api_key="test-ai-key",
        ai_model="chatgpt/gpt-5.2",
        ai_base_url="https://example.test/v1",
        spoonacular_api_key=None,
        spoonacular_base_url="https://api.spoonacular.com",
        posthog_api_key=None,
        posthog_host="https://eu.posthog.com",
        app_env=app_env,  # type: ignore[arg-type]
        log_level="INFO",
    )


def test_build_sentry_monitor_is_disabled_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "aimealplanner.infrastructure.monitoring.sentry.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )

    monitor = build_sentry_monitor(_build_settings(sentry_dsn=None))

    assert monitor == SentryMonitor(enabled=False)
    assert init_calls == []


def test_build_sentry_monitor_initializes_sdk_with_expected_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "aimealplanner.infrastructure.monitoring.sentry.sentry_sdk.init",
        lambda **kwargs: init_calls.append(kwargs),
    )

    monitor = build_sentry_monitor(
        _build_settings(
            sentry_dsn="https://public@example.ingest.sentry.io/1",
            app_env="production",
        ),
    )

    assert monitor == SentryMonitor(enabled=True)
    assert len(init_calls) == 1
    kwargs = init_calls[0]
    assert kwargs["dsn"] == "https://public@example.ingest.sentry.io/1"
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "aimealplanner@0.1.0"
    assert kwargs["send_default_pii"] is False
    assert kwargs["traces_sample_rate"] == 0.2
    assert kwargs["enable_logs"] is True
    assert len(cast(list[object], kwargs["integrations"])) == 2


@pytest.mark.asyncio
async def test_sentry_monitor_flushes_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    flush_calls: list[tuple[float | None, Callable[[int, float], None] | None]] = []

    def fake_flush(
        timeout: float | None = None,
        callback: Callable[[int, float], None] | None = None,
    ) -> None:
        flush_calls.append((timeout, callback))

    monkeypatch.setattr(
        "aimealplanner.infrastructure.monitoring.sentry.sentry_sdk.flush",
        fake_flush,
    )

    await SentryMonitor(enabled=True).aclose()

    assert flush_calls == [(2.0, None)]
