from __future__ import annotations

import pytest
from aimealplanner.core.config import Settings


def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "BOT_TOKEN",
        "DATABASE_URL",
        "REDIS_URL",
        "AI_API_KEY",
        "AI_MODEL",
        "AI_BASE_URL",
        "SPOONACULAR_API_KEY",
        "SPOONACULAR_BASE_URL",
        "APP_ENV",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_settings_load_defaults_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("BOT_TOKEN", "123456:realistic-token")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "chatgpt/gpt-5.2")
    monkeypatch.setenv("AI_BASE_URL", "https://example.test/v1")

    settings = Settings.from_env(env_file=None)

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.ai_model == "chatgpt/gpt-5.2"
    assert settings.ai_base_url == "https://example.test/v1"
    assert settings.spoonacular_api_key is None
    assert settings.spoonacular_base_url == "https://api.spoonacular.com"


def test_settings_reject_placeholder_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("BOT_TOKEN", "123456:REPLACE_ME")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "chatgpt/gpt-5.2")
    monkeypatch.setenv("AI_BASE_URL", "https://example.test/v1")

    with pytest.raises(ValueError):
        Settings.from_env(env_file=None)
