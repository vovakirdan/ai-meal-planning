# ruff: noqa: RUF001
from __future__ import annotations

from datetime import date
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_RECIPE_WEEK_PREFIX = "rpw"
_RECIPE_DAY_PREFIX = "rpd"
_RECIPE_ITEM_PREFIX = "rpi"
_RECIPE_FEEDBACK_PREFIX = "rpf"


def build_recipe_days_keyboard(
    *,
    mode: str,
    weekly_plan_id: UUID,
    days: list[tuple[date, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=build_recipe_day_callback(
                    mode=mode,
                    weekly_plan_id=weekly_plan_id,
                    meal_date=meal_date,
                ),
            ),
        ]
        for meal_date, label in days
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_recipe_items_keyboard(
    *,
    mode: str,
    weekly_plan_id: UUID,
    items: list[tuple[UUID, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=build_recipe_item_callback(
                    mode=mode,
                    planned_meal_item_id=planned_meal_item_id,
                ),
            ),
        ]
        for planned_meal_item_id, label in items
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Назад к дням",
                callback_data=build_recipe_week_callback(
                    mode=mode,
                    weekly_plan_id=weekly_plan_id,
                ),
            ),
        ],
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="Назад к дням",
                callback_data=build_recipe_week_callback(
                    mode=mode,
                    weekly_plan_id=weekly_plan_id,
                ),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_recipe_item_keyboard(
    *,
    mode: str,
    weekly_plan_id: UUID,
    meal_date: date,
    planned_meal_item_id: UUID,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mode == "recipe":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Исправить рецепт",
                    callback_data=build_recipe_feedback_callback(
                        action="start",
                        planned_meal_item_id=planned_meal_item_id,
                    ),
                ),
            ],
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="Назад к блюдам",
                    callback_data=build_recipe_day_callback(
                        mode=mode,
                        weekly_plan_id=weekly_plan_id,
                        meal_date=meal_date,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="К дням недели",
                    callback_data=build_recipe_week_callback(
                        mode=mode,
                        weekly_plan_id=weekly_plan_id,
                    ),
                ),
            ],
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_recipe_feedback_keyboard(*, planned_meal_item_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=build_recipe_feedback_callback(
                        action="cancel",
                        planned_meal_item_id=planned_meal_item_id,
                    ),
                ),
            ],
        ],
    )


def build_recipe_week_callback(*, mode: str, weekly_plan_id: UUID) -> str:
    return f"{_RECIPE_WEEK_PREFIX}:{mode}:{weekly_plan_id.hex}"


def parse_recipe_week_callback(value: str) -> tuple[str, UUID] | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _RECIPE_WEEK_PREFIX or separator == "":
        return None
    mode, separator, weekly_plan_hex = payload.partition(":")
    if separator == "":
        return None
    try:
        return mode, UUID(hex=weekly_plan_hex)
    except ValueError:
        return None


def build_recipe_day_callback(*, mode: str, weekly_plan_id: UUID, meal_date: date) -> str:
    return f"{_RECIPE_DAY_PREFIX}:{mode}:{weekly_plan_id.hex}:{meal_date.isoformat()}"


def parse_recipe_day_callback(value: str) -> tuple[str, UUID, date] | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _RECIPE_DAY_PREFIX or separator == "":
        return None
    mode, separator, remainder = payload.partition(":")
    if separator == "":
        return None
    weekly_plan_hex, separator, meal_date_value = remainder.partition(":")
    if separator == "":
        return None
    try:
        return mode, UUID(hex=weekly_plan_hex), date.fromisoformat(meal_date_value)
    except ValueError:
        return None


def build_recipe_item_callback(*, mode: str, planned_meal_item_id: UUID) -> str:
    return f"{_RECIPE_ITEM_PREFIX}:{mode}:{planned_meal_item_id.hex}"


def parse_recipe_item_callback(value: str) -> tuple[str, UUID] | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _RECIPE_ITEM_PREFIX or separator == "":
        return None
    mode, separator, item_hex = payload.partition(":")
    if separator == "":
        return None
    try:
        return mode, UUID(hex=item_hex)
    except ValueError:
        return None


def build_recipe_feedback_callback(*, action: str, planned_meal_item_id: UUID) -> str:
    return f"{_RECIPE_FEEDBACK_PREFIX}:{action}:{planned_meal_item_id.hex}"


def parse_recipe_feedback_callback(value: str) -> tuple[str, UUID] | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _RECIPE_FEEDBACK_PREFIX or separator == "":
        return None
    action, separator, item_hex = payload.partition(":")
    if separator == "":
        return None
    try:
        return action, UUID(hex=item_hex)
    except ValueError:
        return None
