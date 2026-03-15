from __future__ import annotations

from datetime import date
from uuid import UUID

from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_REVIEW_DAY_PREFIX = "rwd"
_REVIEW_VERDICT_PREFIX = "rwv"
_REVIEW_NEGATIVE_PREFIX = "rwn"


def build_review_days_keyboard(
    weekly_plan_id: UUID,
    days: list[tuple[date, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=build_review_day_callback(weekly_plan_id, meal_date),
            ),
        ]
        for meal_date, label in days
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_review_verdict_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👎",
                    callback_data=build_review_verdict_callback(
                        DishFeedbackVerdict.RARELY_REPEAT,
                    ),
                ),
                InlineKeyboardButton(
                    text="❤️",
                    callback_data=build_review_verdict_callback(DishFeedbackVerdict.FAVORITE),
                ),
                InlineKeyboardButton(
                    text="👍",
                    callback_data=build_review_verdict_callback(DishFeedbackVerdict.CAN_REPEAT),
                ),
            ],
        ],
    )


def build_review_negative_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оставить комментарий",
                    callback_data=build_review_negative_callback("comment"),
                ),
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data=build_review_negative_callback("skip"),
                ),
            ],
        ],
    )


def build_review_comment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data=build_review_negative_callback("skip"),
                ),
            ],
        ],
    )


def build_review_day_callback(weekly_plan_id: UUID, meal_date: date) -> str:
    return f"{_REVIEW_DAY_PREFIX}:{weekly_plan_id.hex}:{meal_date.isoformat()}"


def parse_review_day_callback(value: str) -> tuple[UUID, date] | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _REVIEW_DAY_PREFIX or separator == "":
        return None
    weekly_plan_hex, separator, meal_date_value = payload.partition(":")
    if separator == "":
        return None
    try:
        return UUID(hex=weekly_plan_hex), date.fromisoformat(meal_date_value)
    except ValueError:
        return None


def build_review_verdict_callback(verdict: DishFeedbackVerdict) -> str:
    return f"{_REVIEW_VERDICT_PREFIX}:{verdict.value}"


def parse_review_verdict_callback(value: str) -> DishFeedbackVerdict | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _REVIEW_VERDICT_PREFIX or separator == "":
        return None
    try:
        return DishFeedbackVerdict(payload)
    except ValueError:
        return None


def build_review_negative_callback(action: str) -> str:
    return f"{_REVIEW_NEGATIVE_PREFIX}:{action}"


def parse_review_negative_callback(value: str) -> str | None:
    prefix, separator, payload = value.partition(":")
    if prefix != _REVIEW_NEGATIVE_PREFIX or separator == "":
        return None
    if payload not in {"comment", "skip"}:
        return None
    return payload
