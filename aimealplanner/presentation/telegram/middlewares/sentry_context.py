from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

import sentry_sdk
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update, User


class SentryContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        with sentry_sdk.isolation_scope() as scope:
            self._apply_context(scope, event=event, data=data)
            return await handler(event, data)

    def _apply_context(
        self,
        scope: Any,
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> None:
        user = cast(User | None, data.get("event_from_user"))
        if user is not None:
            user_context: dict[str, str] = {"id": str(user.id)}
            if user.username is not None:
                user_context["username"] = user.username
            if user.language_code is not None:
                user_context["language_code"] = user.language_code
            scope.set_user(user_context)
            scope.set_tag("telegram.user_id", str(user.id))

        chat = cast(Chat | None, data.get("event_chat"))
        if chat is not None:
            scope.set_tag("telegram.chat_id", str(chat.id))
            scope.set_tag("telegram.chat_type", chat.type)

        if isinstance(event, Update):
            self._apply_update_context(scope, event)

    def _apply_update_context(self, scope: Any, update: Update) -> None:
        scope.set_context(
            "telegram_update",
            {
                "update_id": update.update_id,
                "has_message": update.message is not None,
                "has_callback_query": update.callback_query is not None,
            },
        )

        command = _extract_command(update.message)
        if command is not None:
            scope.set_tag("telegram.command", command)

        callback_prefix = _extract_callback_prefix(update.callback_query)
        if callback_prefix is not None:
            scope.set_tag("telegram.callback_prefix", callback_prefix)


def _extract_command(message: Message | None) -> str | None:
    if message is None or message.text is None:
        return None
    text = message.text.strip()
    if not text.startswith("/"):
        return None
    command_token = text.split(maxsplit=1)[0]
    return command_token.removeprefix("/").split("@", maxsplit=1)[0]


def _extract_callback_prefix(callback: CallbackQuery | None) -> str | None:
    if callback is None or callback.data is None:
        return None
    return callback.data.split(":", maxsplit=1)[0]
