from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SQLAlchemyEnum


class RepeatabilityMode(StrEnum):
    BALANCED = "balanced"
    MORE_VARIETY = "more_variety"
    MORE_REPEATABILITY = "more_repeatability"


class PantryStockLevel(StrEnum):
    HAS = "has"
    LOW = "low"
    NONE = "none"


class WeeklyPlanStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"


class MealSlot(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK_1 = "snack_1"
    SNACK_2 = "snack_2"
    DESSERT = "dessert"


class PlannedMealStatus(StrEnum):
    PLANNED = "planned"
    REPLACED = "replaced"
    SKIPPED = "skipped"
    PREPARED = "prepared"


class DishFeedbackVerdict(StrEnum):
    NEVER_AGAIN = "never_again"
    RARELY_REPEAT = "rarely_repeat"
    CAN_REPEAT = "can_repeat"
    FAVORITE = "favorite"


class ShoppingListAvailabilityStatus(StrEnum):
    NEED_TO_BUY = "need_to_buy"
    PARTIALLY_HAVE = "partially_have"
    ALREADY_HAVE = "already_have"


def build_str_enum(enum_cls: type[StrEnum], *, name: str) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_cls,
        name=name,
        values_callable=lambda items: [item.value for item in items],
        validate_strings=True,
    )
