from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StoredPlanDaySummary:
    meal_date: date
    meals_count: int


@dataclass(frozen=True, slots=True)
class StoredPlanOverview:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    days: list[StoredPlanDaySummary]


@dataclass(frozen=True, slots=True)
class StoredPlanMealSummary:
    planned_meal_id: UUID
    slot: str
    note: str | None
    item_names: list[str]


@dataclass(frozen=True, slots=True)
class StoredPlanDayView:
    weekly_plan_id: UUID
    meal_date: date
    meals: list[StoredPlanMealSummary]


@dataclass(frozen=True, slots=True)
class StoredMealItemSummary:
    planned_meal_item_id: UUID
    position: int
    name: str


@dataclass(frozen=True, slots=True)
class StoredPlanMealView:
    weekly_plan_id: UUID
    planned_meal_id: UUID
    meal_date: date
    slot: str
    note: str | None
    items: list[StoredMealItemSummary]


@dataclass(frozen=True, slots=True)
class StoredPlanItemView:
    weekly_plan_id: UUID
    planned_meal_id: UUID
    planned_meal_item_id: UUID
    meal_date: date
    slot: str
    name: str
    summary: str | None
    adaptation_notes: list[str]
    snapshot_payload: dict[str, Any]
