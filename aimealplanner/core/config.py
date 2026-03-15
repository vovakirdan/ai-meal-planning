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
_DEFAULT_SPOONACULAR_BASE_URL = "https://api.spoonacular.com"
_DEFAULT_POSTHOG_HOST = "https://eu.posthog.com"


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_url: str
    redis_url: str
    ai_api_key: str
    ai_model: str
    ai_base_url: str
    spoonacular_api_key: str | None
    spoonacular_base_url: str
    posthog_api_key: str | None
    posthog_host: str
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

        ai_api_key = os.getenv("AI_API_KEY", "").strip()
        if not ai_api_key:
            raise ValueError("AI_API_KEY is required")

        ai_model = os.getenv("AI_MODEL", "").strip()
        if not ai_model:
            raise ValueError("AI_MODEL is required")

        ai_base_url = os.getenv("AI_BASE_URL", "").strip()
        if not ai_base_url:
            raise ValueError("AI_BASE_URL is required")

        spoonacular_api_key = os.getenv("SPOONACULAR_API_KEY", "").strip() or None
        posthog_api_key = os.getenv("POSTHOG_API_KEY", "").strip() or None

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
            ai_api_key=ai_api_key,
            ai_model=ai_model,
            ai_base_url=ai_base_url,
            spoonacular_api_key=spoonacular_api_key,
            spoonacular_base_url=os.getenv(
                "SPOONACULAR_BASE_URL",
                _DEFAULT_SPOONACULAR_BASE_URL,
            ),
            posthog_api_key=posthog_api_key,
            posthog_host=os.getenv("POSTHOG_HOST", _DEFAULT_POSTHOG_HOST),
            app_env=cast(AppEnv, app_env),
            log_level=log_level,
        )
