from __future__ import annotations

import pytest
from aimealplanner.core.config import Settings


def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("BOT_TOKEN", "DATABASE_URL", "REDIS_URL", "APP_ENV", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)


def test_settings_load_defaults_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("BOT_TOKEN", "123456:realistic-token")

    settings = Settings.from_env(env_file=None)

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")


def test_settings_reject_placeholder_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("BOT_TOKEN", "123456:REPLACE_ME")

    with pytest.raises(ValueError):
        Settings.from_env(env_file=None)
