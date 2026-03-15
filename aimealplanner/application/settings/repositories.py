from __future__ import annotations

from collections.abc import Callable
from datetime import time
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.onboarding.dto import PantryItemInput
from aimealplanner.application.settings.dto import (
    NewSettingsMemberInput,
    StoredSettingsDishPolicy,
    StoredSettingsHousehold,
    StoredSettingsMember,
    StoredSettingsPantryItem,
    StoredSettingsUser,
)
from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    PantryStockLevel,
    RepeatabilityMode,
)


class SettingsRepository(Protocol):
    async def get_user_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> StoredSettingsUser | None: ...

    async def get_household_by_user_id(self, user_id: UUID) -> StoredSettingsHousehold | None: ...

    async def update_household_planning_settings(
        self,
        household_id: UUID,
        *,
        meal_count_per_day: int,
        desserts_enabled: bool,
        repeatability_mode: RepeatabilityMode,
    ) -> None: ...

    async def update_daily_feedback_reminder(
        self,
        user_id: UUID,
        reminder_time: time | None,
    ) -> None: ...

    async def update_weekly_planning_reminder(
        self,
        user_id: UUID,
        day_of_week: int | None,
        reminder_time: time | None,
    ) -> None: ...

    async def list_members(self, household_id: UUID) -> list[StoredSettingsMember]: ...

    async def get_member(
        self,
        household_id: UUID,
        member_id: UUID,
    ) -> StoredSettingsMember | None: ...

    async def add_member(
        self,
        household_id: UUID,
        member: NewSettingsMemberInput,
    ) -> StoredSettingsMember: ...

    async def rename_member(
        self,
        household_id: UUID,
        member_id: UUID,
        display_name: str,
    ) -> StoredSettingsMember: ...

    async def set_member_active(
        self,
        household_id: UUID,
        member_id: UUID,
        is_active: bool,
    ) -> StoredSettingsMember: ...

    async def update_member_constraints(
        self,
        household_id: UUID,
        member_id: UUID,
        constraints: list[str],
    ) -> StoredSettingsMember: ...

    async def update_member_cuisines(
        self,
        household_id: UUID,
        member_id: UUID,
        favorite_cuisines: list[str],
    ) -> StoredSettingsMember: ...

    async def update_member_note(
        self,
        household_id: UUID,
        member_id: UUID,
        profile_note: str | None,
    ) -> StoredSettingsMember: ...

    async def list_pantry_items(self, household_id: UUID) -> list[StoredSettingsPantryItem]: ...

    async def get_pantry_item(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> StoredSettingsPantryItem | None: ...

    async def add_or_update_pantry_item(
        self,
        household_id: UUID,
        pantry_item: PantryItemInput,
    ) -> StoredSettingsPantryItem: ...

    async def update_pantry_item_stock(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        stock_level: PantryStockLevel,
    ) -> StoredSettingsPantryItem: ...

    async def update_pantry_item_note(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        note: str | None,
    ) -> StoredSettingsPantryItem: ...

    async def update_pantry_item_quantity(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        *,
        quantity_value: Decimal | None,
        quantity_unit: str | None,
        note: str | None,
    ) -> StoredSettingsPantryItem: ...

    async def delete_pantry_item(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> None: ...

    async def list_dish_policies(
        self,
        household_id: UUID,
        verdict: DishFeedbackVerdict | None = None,
    ) -> list[StoredSettingsDishPolicy]: ...

    async def get_dish_policy(
        self,
        household_id: UUID,
        policy_id: UUID,
    ) -> StoredSettingsDishPolicy | None: ...

    async def delete_dish_policy(
        self,
        household_id: UUID,
        policy_id: UUID,
    ) -> None: ...


SettingsRepositoryFactory = Callable[[AsyncSession], SettingsRepository]
