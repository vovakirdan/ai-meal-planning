from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    PantryStockLevel,
    RepeatabilityMode,
)


@dataclass(frozen=True, slots=True)
class StoredSettingsUser:
    id: UUID
    telegram_user_id: int
    timezone: str
    daily_feedback_reminder_enabled: bool
    daily_feedback_reminder_time: time | None
    weekly_planning_reminder_enabled: bool
    weekly_planning_reminder_day_of_week: int | None
    weekly_planning_reminder_time: time | None


@dataclass(frozen=True, slots=True)
class StoredSettingsHousehold:
    id: UUID
    user_id: UUID
    onboarding_completed_at: datetime | None
    default_meal_count_per_day: int
    desserts_enabled: bool
    repeatability_mode: RepeatabilityMode


@dataclass(frozen=True, slots=True)
class StoredSettingsMember:
    id: UUID
    household_id: UUID
    display_name: str
    sort_order: int
    constraints: list[str]
    favorite_cuisines: list[str]
    profile_note: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class StoredSettingsPantryItem:
    id: UUID
    ingredient_id: UUID
    ingredient_name: str
    stock_level: PantryStockLevel
    quantity_value: Decimal | None
    quantity_unit: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class StoredSettingsDishPolicy:
    id: UUID
    dish_id: UUID
    dish_name: str
    verdict: DishFeedbackVerdict
    note: str | None


@dataclass(frozen=True, slots=True)
class NewSettingsMemberInput:
    display_name: str
    constraints: list[str]
    favorite_cuisines: list[str]
    profile_note: str | None


@dataclass(frozen=True, slots=True)
class SettingsHomeView:
    user: StoredSettingsUser
    household: StoredSettingsHousehold
    active_members_count: int
    inactive_members_count: int
    pantry_items_count: int
    favorite_policies_count: int
    blocked_policies_count: int


@dataclass(frozen=True, slots=True)
class FamilySettingsView:
    household: StoredSettingsHousehold
    active_members: list[StoredSettingsMember]
    inactive_members: list[StoredSettingsMember]


@dataclass(frozen=True, slots=True)
class MemberSettingsView:
    member: StoredSettingsMember


@dataclass(frozen=True, slots=True)
class PantrySettingsView:
    items: list[StoredSettingsPantryItem]


@dataclass(frozen=True, slots=True)
class DishPolicySettingsView:
    verdict: DishFeedbackVerdict
    items: list[StoredSettingsDishPolicy]


@dataclass(frozen=True, slots=True)
class DishPolicyDetailView:
    policy: StoredSettingsDishPolicy
