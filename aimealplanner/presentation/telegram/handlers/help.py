from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aimealplanner.presentation.telegram.commands import render_help_text
from aimealplanner.presentation.telegram.keyboards.onboarding import remove_keyboard


def build_help_router() -> Router:
    router = Router(name="help")

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        await message.answer(
            render_help_text(),
            reply_markup=remove_keyboard(),
            parse_mode="Markdown",
        )

    return router
