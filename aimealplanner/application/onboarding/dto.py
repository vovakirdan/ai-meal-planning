from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from aimealplanner.infrastructure.db.enums import PantryStockLevel, RepeatabilityMode


@dataclass(frozen=True, slots=True)
class StoredUser:
    id: UUID
    telegram_user_id: int
    timezone: str


@dataclass(frozen=True, slots=True)
class StoredHousehold:
    id: UUID
    user_id: UUID
    onboarding_completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredIngredient:
    id: UUID
    canonical_name: str
    normalized_name: str


@dataclass(frozen=True, slots=True)
class OnboardingStartResult:
    user_id: UUID
    household_id: UUID
    already_completed: bool


@dataclass(frozen=True, slots=True)
class HouseholdSettingsInput:
    meal_count_per_day: int
    desserts_enabled: bool
    repeatability_mode: RepeatabilityMode


@dataclass(frozen=True, slots=True)
class HouseholdMemberInput:
    sort_order: int
    display_name: str
    constraints: list[str]
    favorite_cuisines: list[str]
    profile_note: str | None


@dataclass(frozen=True, slots=True)
class DailyReminderInput:
    reminder_time: time | None


@dataclass(frozen=True, slots=True)
class WeeklyReminderInput:
    day_of_week: int | None
    reminder_time: time | None


@dataclass(frozen=True, slots=True)
class PantryItemInput:
    ingredient_name: str
    normalized_name: str
    stock_level: PantryStockLevel
    quantity_value: Decimal | None
    quantity_unit: str | None
    note: str | None
