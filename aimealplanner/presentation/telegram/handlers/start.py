from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from aimealplanner.application.greeting import build_welcome_message

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(build_welcome_message())
