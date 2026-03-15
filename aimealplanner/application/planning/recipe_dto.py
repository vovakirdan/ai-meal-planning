from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from aimealplanner.infrastructure.db.enums import WeeklyPlanStatus


@dataclass(frozen=True, slots=True)
class RecipeIngredient:
    name: str
    amount: str | None
    preparation_note: str | None


@dataclass(frozen=True, slots=True)
class RecipeDetails:
    summary: str | None
    ingredients: list[RecipeIngredient]
    preparation_steps: list[str]
    cooking_steps: list[str]
    serving_steps: list[str]
    prep_time_minutes: int | None
    cook_time_minutes: int | None
    serving_notes: str | None


@dataclass(frozen=True, slots=True)
class RecipeDayOption:
    meal_date: date
    items_count: int


@dataclass(frozen=True, slots=True)
class RecipeStartContext:
    weekly_plan_id: UUID
    status: WeeklyPlanStatus
    start_date: date
    end_date: date
    days: list[RecipeDayOption]


@dataclass(frozen=True, slots=True)
class RecipeItemOption:
    planned_meal_item_id: UUID
    meal_date: date
    slot: str
    dish_name: str


@dataclass(frozen=True, slots=True)
class RecipeDayContext:
    weekly_plan_id: UUID
    meal_date: date
    items: list[RecipeItemOption]
