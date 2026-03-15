# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from itertools import cycle

from aiogram import Router
from aiogram.client.bot import Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.analytics import AnalyticsTracker
from aimealplanner.application.planning import (
    RecipeService,
    ShoppingListService,
    render_shopping_list,
)
from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.db.repositories import build_planning_repositories
from aimealplanner.infrastructure.recipes import SpoonacularRecipeHintProvider
from aimealplanner.presentation.telegram.analytics import track_command, track_message_event
from aimealplanner.presentation.telegram.keyboards.onboarding import remove_keyboard

logger = logging.getLogger(__name__)
_SHOPPING_PROGRESS_TEXTS = (
    "Собираю корзину и проверяю ингредиенты...",
    "Все еще собираю корзину: уточняю ингредиенты по блюдам.",
    "Все еще работаю: сверяю покупки с запасами дома.",
    "Почти готово: собираю итоговый список покупок.",
)
_PROGRESS_MESSAGE_INTERVAL_SECONDS = 20
_TELEGRAM_TEXT_LIMIT = 4096
_SHOPPING_CHUNK_TARGET = 3500


def build_shopping_router(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
    recipe_hint_provider: SpoonacularRecipeHintProvider | None,
    analytics: AnalyticsTracker,
) -> Router:
    router = Router(name="shopping")
    recipe_service = RecipeService(
        session_factory,
        build_planning_repositories,
        recipe_client=weekly_plan_generator,
        recipe_hint_provider=recipe_hint_provider,
    )
    shopping_service = ShoppingListService(
        session_factory,
        build_planning_repositories,
        recipe_warmer=recipe_service,
    )

    @router.message(Command("shopping"))
    async def handle_shopping_command(message: Message) -> None:
        track_command(analytics, message=message, command="shopping")
        await message.answer(
            _SHOPPING_PROGRESS_TEXTS[0],
            reply_markup=remove_keyboard(),
        )
        heartbeat_task = asyncio.create_task(_send_progress_updates(message))
        async with ChatActionSender.typing(
            bot=_require_message_bot(message),
            chat_id=message.chat.id,
        ):
            try:
                result = await shopping_service.generate_for_latest_visible_week(
                    _require_telegram_user_id_from_message(message),
                )
            except ValueError as err:
                await _stop_progress_updates(heartbeat_task)
                await message.answer(str(err))
                return
            except Exception:
                logger.exception("failed to generate shopping list")
                await _stop_progress_updates(heartbeat_task)
                await message.answer(
                    "Не получилось собрать корзину. Попробуй еще раз чуть позже.",
                )
                return

        await _stop_progress_updates(heartbeat_task)
        availability_counts = {
            "need_to_buy_count": 0,
            "partially_have_count": 0,
            "already_have_count": 0,
        }
        for item in result.items:
            availability_counts[f"{item.availability_status.value}_count"] += 1
        track_message_event(
            analytics,
            message=message,
            event="shopping_generated",
            properties={"items_count": len(result.items), **availability_counts},
        )
        for chunk in _split_shopping_message(render_shopping_list(result)):
            await message.answer(chunk)

    return router


def _require_telegram_user_id_from_message(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram user is unavailable")
    return message.from_user.id


def _require_message_bot(message: Message) -> Bot:
    if message.bot is None:
        raise ValueError("Telegram bot is unavailable")
    return message.bot


async def _send_progress_updates(message: Message) -> None:
    for progress_text in cycle(_SHOPPING_PROGRESS_TEXTS[1:]):
        await asyncio.sleep(_PROGRESS_MESSAGE_INTERVAL_SECONDS)
        await message.answer(progress_text)


async def _stop_progress_updates(progress_task: asyncio.Task[None]) -> None:
    progress_task.cancel()
    with suppress(asyncio.CancelledError):
        await progress_task


def _split_shopping_message(text: str) -> list[str]:
    if len(text) <= _TELEGRAM_TEXT_LIMIT:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for line in text.splitlines():
        line_length = len(line) + 1
        if current_lines and current_length + line_length > _SHOPPING_CHUNK_TARGET:
            chunks.append("\n".join(current_lines).strip())
            current_lines = []
            current_length = 0
        current_lines.append(line)
        current_length += line_length

    if current_lines:
        chunks.append("\n".join(current_lines).strip())

    if len(chunks) == 1 and len(chunks[0]) <= _TELEGRAM_TEXT_LIMIT:
        return chunks

    return [
        f"Список покупок ({index}/{len(chunks)}).\n\n{chunk}"
        for index, chunk in enumerate(chunks, start=1)
    ]
