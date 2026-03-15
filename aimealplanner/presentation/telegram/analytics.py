from __future__ import annotations

from aiogram.types import CallbackQuery, Message, User

from aimealplanner.application.analytics import AnalyticsProperties, AnalyticsTracker


def track_command(
    analytics: AnalyticsTracker,
    *,
    message: Message,
    command: str,
    properties: AnalyticsProperties | None = None,
) -> None:
    user = message.from_user
    if user is None:
        return

    _identify_user(analytics, user)
    analytics.capture(
        telegram_user_id=user.id,
        event="command_invoked",
        properties={"command": command, **dict(properties or {})},
    )


def track_message_event(
    analytics: AnalyticsTracker,
    *,
    message: Message,
    event: str,
    properties: AnalyticsProperties | None = None,
) -> None:
    user = message.from_user
    if user is None:
        return

    _identify_user(analytics, user)
    analytics.capture(
        telegram_user_id=user.id,
        event=event,
        properties=properties,
    )


def track_callback_event(
    analytics: AnalyticsTracker,
    *,
    callback: CallbackQuery,
    event: str,
    properties: AnalyticsProperties | None = None,
) -> None:
    user = callback.from_user
    if user is None:
        return

    _identify_user(analytics, user)
    analytics.capture(
        telegram_user_id=user.id,
        event=event,
        properties=properties,
    )


def track_telegram_user_event(
    analytics: AnalyticsTracker,
    *,
    telegram_user_id: int,
    event: str,
    properties: AnalyticsProperties | None = None,
) -> None:
    analytics.capture(
        telegram_user_id=telegram_user_id,
        event=event,
        properties=properties,
    )


def _identify_user(analytics: AnalyticsTracker, user: User) -> None:
    properties: dict[str, object] = {}
    if user.username is not None:
        properties["telegram_username"] = user.username
    if user.language_code is not None:
        properties["telegram_language_code"] = user.language_code
    analytics.identify(
        telegram_user_id=user.id,
        properties=properties,
    )
