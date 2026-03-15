from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from aimealplanner.infrastructure.db.enums import PantryStockLevel, RepeatabilityMode


@dataclass(frozen=True, slots=True)
class PlanningMemberContext:
    display_name: str
    constraints: list[str]
    favorite_cuisines: list[str]
    profile_note: str | None


@dataclass(frozen=True, slots=True)
class PlanningPantryItemContext:
    ingredient_name: str
    stock_level: PantryStockLevel
    quantity_value: Decimal | None
    quantity_unit: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class WeeklyPlanGenerationContext:
    weekly_plan_id: UUID
    household_id: UUID
    timezone: str
    start_date: date
    end_date: date
    meal_count_per_day: int
    desserts_enabled: bool
    repeatability_mode: RepeatabilityMode
    active_slots: list[str]
    week_mood: str | None
    weekly_notes: str | None
    pantry_considered: bool
    context_payload: dict[str, Any]
    members: list[PlanningMemberContext]
    pantry_items: list[PlanningPantryItemContext]


@dataclass(frozen=True, slots=True)
class GeneratedMealItem:
    name: str
    summary: str
    adaptation_notes: list[str]


@dataclass(frozen=True, slots=True)
class GeneratedMeal:
    meal_date: date
    slot: str
    note: str | None
    items: list[GeneratedMealItem]


@dataclass(frozen=True, slots=True)
class GeneratedWeekPlan:
    meals: list[GeneratedMeal]


class WeeklyPlanGenerationClient(Protocol):
    async def generate_week_plan(
        self,
        context: WeeklyPlanGenerationContext,
    ) -> GeneratedWeekPlan: ...
