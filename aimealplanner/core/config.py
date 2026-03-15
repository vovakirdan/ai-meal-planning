from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

from dotenv import load_dotenv

AppEnv = Literal["development", "test", "production"]
_ALLOWED_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
_ALLOWED_APP_ENVS = {"development", "test", "production"}
_DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://aimealplanner:aimealplanner@postgres:5432/aimealplanner"
)
_DEFAULT_REDIS_URL = "redis://redis:6379/0"


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_url: str
    redis_url: str
    app_env: AppEnv
    log_level: str

    @classmethod
    def from_env(cls, env_file: str | None = ".env") -> Settings:
        if env_file is not None:
            load_dotenv(env_file, override=False)

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("BOT_TOKEN is required")
        if "REPLACE_ME" in bot_token or "TEST_TOKEN" in bot_token:
            raise ValueError("BOT_TOKEN must contain a real Telegram bot token")

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in _ALLOWED_LOG_LEVELS:
            raise ValueError(
                f"LOG_LEVEL must be one of: {', '.join(sorted(_ALLOWED_LOG_LEVELS))}",
            )

        app_env = os.getenv("APP_ENV", "development")
        if app_env not in _ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV must be one of: {', '.join(sorted(_ALLOWED_APP_ENVS))}",
            )

        return cls(
            bot_token=bot_token,
            database_url=os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL),
            redis_url=os.getenv("REDIS_URL", _DEFAULT_REDIS_URL),
            app_env=cast(AppEnv, app_env),
            log_level=log_level,
        )
