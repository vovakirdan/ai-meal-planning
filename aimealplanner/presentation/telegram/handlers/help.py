from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aimealplanner.application.analytics import AnalyticsTracker
from aimealplanner.presentation.telegram.analytics import track_command, track_message_event
from aimealplanner.presentation.telegram.commands import render_help_text
from aimealplanner.presentation.telegram.keyboards.onboarding import remove_keyboard


def build_help_router(*, analytics: AnalyticsTracker) -> Router:
    router = Router(name="help")

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        track_command(analytics, message=message, command="help")
        track_message_event(analytics, message=message, event="help_viewed")
        await message.answer(
            render_help_text(),
            reply_markup=remove_keyboard(),
            parse_mode="Markdown",
        )

    return router
