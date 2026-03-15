from __future__ import annotations

import pytest
from aimealplanner.application.analytics import NullAnalyticsTracker
from aimealplanner.core.config import Settings
from aimealplanner.infrastructure.analytics.posthog import (
    PosthogAnalyticsTracker,
    build_analytics_tracker,
)


class _FakePosthogClient:
    def __init__(self) -> None:
        self.capture_calls: list[dict[str, object]] = []
        self.set_calls: list[dict[str, object]] = []
        self.shutdown_calls = 0

    def capture(self, event: str, **kwargs: object) -> str:
        self.capture_calls.append({"event": event, **kwargs})
        return "ok"

    def set(self, **kwargs: object) -> str:
        self.set_calls.append(kwargs)
        return "ok"

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def _build_settings(*, posthog_api_key: str | None) -> Settings:
    return Settings(
        bot_token="123456:realistic-token",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        sentry_dsn=None,
        ai_api_key="test-ai-key",
        ai_model="chatgpt/gpt-5.2",
        ai_base_url="https://example.test/v1",
        spoonacular_api_key=None,
        spoonacular_base_url="https://api.spoonacular.com",
        posthog_api_key=posthog_api_key,
        posthog_host="https://eu.posthog.com",
        app_env="development",
        log_level="INFO",
    )


def test_build_analytics_tracker_returns_null_without_api_key() -> None:
    tracker = build_analytics_tracker(_build_settings(posthog_api_key=None))

    assert isinstance(tracker, NullAnalyticsTracker)


@pytest.mark.asyncio
async def test_build_analytics_tracker_uses_posthog_client_and_tracks_events() -> None:
    created_kwargs: dict[str, object] = {}
    client = _FakePosthogClient()

    def fake_factory(**kwargs: object) -> _FakePosthogClient:
        created_kwargs.update(kwargs)
        return client

    tracker = build_analytics_tracker(
        _build_settings(posthog_api_key="phc_test_key"),
        client_factory=fake_factory,
    )

    assert isinstance(tracker, PosthogAnalyticsTracker)
    assert created_kwargs["project_api_key"] == "phc_test_key"
    assert created_kwargs["host"] == "https://eu.posthog.com"
    assert created_kwargs["disable_geoip"] is True

    tracker.identify(
        telegram_user_id=42,
        properties={"telegram_username": "chef"},
    )
    tracker.capture(
        telegram_user_id=42,
        event="plan_generated",
        properties={"items_count": 12},
    )
    await tracker.aclose()

    assert client.set_calls == [
        {
            "distinct_id": "telegram:42",
            "properties": {
                "source": "telegram",
                "app_env": "development",
                "telegram_user_id": 42,
                "telegram_username": "chef",
            },
        },
    ]
    assert client.capture_calls == [
        {
            "event": "plan_generated",
            "distinct_id": "telegram:42",
            "properties": {
                "source": "telegram",
                "app_env": "development",
                "items_count": 12,
            },
        },
    ]
    assert client.shutdown_calls == 1
