from __future__ import annotations

from aimealplanner.presentation.telegram.keyboards.onboarding import (
    SKIP_LABEL,
    _keyboard,
)
from aiogram.types import ReplyKeyboardMarkup

NEXT_WEEK_LABEL = "Следующая неделя"
TODAY_LABEL = "С сегодня"
TOMORROW_LABEL = "С завтра"
CUSTOM_DATES_LABEL = "Свои даты"

WEEK_MOOD_LABELS = {
    "Азиатская": "Азиатская",
    "Мексиканская": "Мексиканская",
    "Русская": "Русская",
    "Постное меню": "Постное меню",
    "Средиземноморская": "Средиземноморская",
}


def build_range_choice_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard(
        [
            [NEXT_WEEK_LABEL],
            [TODAY_LABEL, TOMORROW_LABEL],
            [CUSTOM_DATES_LABEL],
        ],
    )


def build_week_mood_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard(
        [
            ["Азиатская", "Мексиканская"],
            ["Русская", "Постное меню"],
            ["Средиземноморская"],
            [SKIP_LABEL],
        ],
    )
