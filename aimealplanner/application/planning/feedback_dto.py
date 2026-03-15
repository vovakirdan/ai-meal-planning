from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ReviewDayOption:
    meal_date: date
    meals_count: int
    items_count: int


@dataclass(frozen=True, slots=True)
class ReviewStartContext:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    days: list[ReviewDayOption]


@dataclass(frozen=True, slots=True)
class ReviewQueueEntry:
    planned_meal_item_id: UUID
    meal_date: date
    slot: str
    dish_name: str
    household_member_id: UUID
    household_member_name: str


@dataclass(frozen=True, slots=True)
class ReviewDaySession:
    weekly_plan_id: UUID
    meal_date: date
    entries: list[ReviewQueueEntry]
