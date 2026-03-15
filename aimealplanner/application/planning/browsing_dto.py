from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from aimealplanner.application.planning.generation_dto import DishQuickAction
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict


@dataclass(frozen=True, slots=True)
class StoredPlanDaySummary:
    meal_date: date
    meals_count: int
    meals: list[StoredPlanMealSummary] = field(default_factory=list)


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
    dish_id: UUID | None
    meal_date: date
    slot: str
    name: str
    summary: str | None
    adaptation_notes: list[str]
    snapshot_payload: dict[str, Any]
    suggested_actions: list[DishQuickAction]
    household_policy_verdict: DishFeedbackVerdict | None
    household_policy_note: str | None
