from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from aimealplanner.infrastructure.db.enums import RepeatabilityMode


@dataclass(frozen=True, slots=True)
class StoredPlanningUser:
    id: UUID
    telegram_user_id: int
    timezone: str


@dataclass(frozen=True, slots=True)
class StoredPlanningHousehold:
    id: UUID
    user_id: UUID
    onboarding_completed_at: datetime | None
    default_meal_count_per_day: int
    desserts_enabled: bool
    repeatability_mode: RepeatabilityMode
    pantry_items_count: int


@dataclass(frozen=True, slots=True)
class StoredDraftPlan:
    id: UUID
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class PlanningStartContext:
    timezone: str
    today_local_date: date
    default_start_date: date
    default_end_date: date
    default_meal_count_per_day: int
    default_desserts_enabled: bool
    pantry_items_count: int
    existing_draft: StoredDraftPlan | None


@dataclass(frozen=True, slots=True)
class PlanDraftInput:
    start_date: date
    end_date: date
    meal_count_per_day: int
    desserts_enabled: bool
    week_mood: str | None
    weekly_notes: str | None
    pantry_considered: bool
    context_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PlanDraftResult:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    active_slots: list[str]
    pantry_considered: bool
