from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from aimealplanner.presentation.telegram.keyboards.onboarding import (
    SKIP_LABEL,
    _keyboard,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

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

_PLAN_WEEK_PREFIX = "pw"
_PLAN_DAY_PREFIX = "pd"
_PLAN_MEAL_PREFIX = "pm"
_PLAN_ITEM_PREFIX = "pi"


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


def build_plan_days_keyboard(
    weekly_plan_id: UUID,
    start_date: date,
    end_date: date,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_date = start_date
    while current_date <= end_date:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_format_day_button_label(current_date),
                    callback_data=build_plan_day_callback(weekly_plan_id, current_date),
                ),
            ],
        )
        current_date += timedelta(days=1)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_plan_day_keyboard(
    weekly_plan_id: UUID,
    meals: list[tuple[UUID, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=build_plan_meal_callback(planned_meal_id),
            ),
        ]
        for planned_meal_id, label in meals
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Назад к дням",
                callback_data=build_plan_week_callback(weekly_plan_id),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_plan_meal_keyboard(
    weekly_plan_id: UUID,
    meal_date: date,
    items: list[tuple[UUID, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=build_plan_item_callback(planned_meal_item_id),
            ),
        ]
        for planned_meal_item_id, label in items
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Назад к дню",
                callback_data=build_plan_day_callback(weekly_plan_id, meal_date),
            ),
        ],
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="К дням недели",
                callback_data=build_plan_week_callback(weekly_plan_id),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_plan_item_keyboard(
    weekly_plan_id: UUID,
    meal_date: date,
    planned_meal_id: UUID,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Назад к блюдам приема пищи",
                    callback_data=build_plan_meal_callback(planned_meal_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Назад к дню",
                    callback_data=build_plan_day_callback(weekly_plan_id, meal_date),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="К дням недели",
                    callback_data=build_plan_week_callback(weekly_plan_id),
                ),
            ],
        ],
    )


def build_plan_week_callback(weekly_plan_id: UUID) -> str:
    return f"{_PLAN_WEEK_PREFIX}:{weekly_plan_id.hex}"


def build_plan_day_callback(weekly_plan_id: UUID, meal_date: date) -> str:
    return f"{_PLAN_DAY_PREFIX}:{weekly_plan_id.hex}:{meal_date.strftime('%Y%m%d')}"


def build_plan_meal_callback(planned_meal_id: UUID) -> str:
    return f"{_PLAN_MEAL_PREFIX}:{planned_meal_id.hex}"


def build_plan_item_callback(planned_meal_item_id: UUID) -> str:
    return f"{_PLAN_ITEM_PREFIX}:{planned_meal_item_id.hex}"


def parse_plan_week_callback(value: str) -> UUID | None:
    return _parse_uuid_callback(value, prefix=_PLAN_WEEK_PREFIX, expected_parts=2)


def parse_plan_day_callback(value: str) -> tuple[UUID, date] | None:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != _PLAN_DAY_PREFIX:
        return None
    weekly_plan_id = _parse_uuid_hex(parts[1])
    if weekly_plan_id is None:
        return None
    try:
        meal_date = date(
            year=int(parts[2][0:4]),
            month=int(parts[2][4:6]),
            day=int(parts[2][6:8]),
        )
    except ValueError:
        return None
    return (weekly_plan_id, meal_date)


def parse_plan_meal_callback(value: str) -> UUID | None:
    return _parse_uuid_callback(value, prefix=_PLAN_MEAL_PREFIX, expected_parts=2)


def parse_plan_item_callback(value: str) -> UUID | None:
    return _parse_uuid_callback(value, prefix=_PLAN_ITEM_PREFIX, expected_parts=2)


def _parse_uuid_callback(value: str, *, prefix: str, expected_parts: int) -> UUID | None:
    parts = value.split(":")
    if len(parts) != expected_parts or parts[0] != prefix:
        return None
    return _parse_uuid_hex(parts[1])


def _parse_uuid_hex(value: str) -> UUID | None:
    try:
        return UUID(hex=value)
    except ValueError:
        return None


def _format_day_button_label(value: date) -> str:
    weekdays = [
        "Пн",
        "Вт",
        "Ср",
        "Чт",
        "Пт",
        "Сб",
        "Вс",
    ]
    return f"{weekdays[value.weekday()]} {value.strftime('%d.%m')}"
