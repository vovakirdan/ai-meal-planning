from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

YES_LABEL = "Да"
NO_LABEL = "Нет"
SKIP_LABEL = "Пропустить"

REPEATABILITY_LABELS = {
    "Сбалансировано": "balanced",
    "Больше разнообразия": "more_variety",
    "Больше повторяемости": "more_repeatability",
}

PANTRY_STOCK_LABELS = {
    "Есть": "has",
    "Мало": "low",
    "Нет": "none",
}

DAY_OF_WEEK_LABELS = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def build_household_size_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard([["1", "2", "3"], ["4", "5"]])


def build_meal_count_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard([["2", "3", "4", "5"]])


def build_yes_no_keyboard(*, allow_skip: bool = False) -> ReplyKeyboardMarkup:
    rows = [[YES_LABEL, NO_LABEL]]
    if allow_skip:
        rows.append([SKIP_LABEL])
    return _keyboard(rows)


def build_repeatability_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard(
        [
            ["Сбалансировано"],
            ["Больше разнообразия"],
            ["Больше повторяемости"],
            [SKIP_LABEL],
        ],
    )


def build_skip_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard([[SKIP_LABEL]])


def build_day_of_week_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard(
        [
            DAY_OF_WEEK_LABELS[:3],
            DAY_OF_WEEK_LABELS[3:5],
            DAY_OF_WEEK_LABELS[5:],
        ],
    )


def build_pantry_stock_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard([list(PANTRY_STOCK_LABELS)])


def build_pantry_continue_keyboard() -> ReplyKeyboardMarkup:
    return _keyboard([[YES_LABEL, NO_LABEL]])


def _keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in rows],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
