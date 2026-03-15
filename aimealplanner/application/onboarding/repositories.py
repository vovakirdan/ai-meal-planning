from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.onboarding.dto import (
    HouseholdMemberInput,
    HouseholdSettingsInput,
    PantryItemInput,
    StoredHousehold,
    StoredIngredient,
    StoredUser,
)


class UserOnboardingRepository(Protocol):
    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredUser | None: ...

    async def create(self, telegram_user_id: int, timezone: str) -> StoredUser: ...

    async def reset_reminders(self, user_id: UUID) -> None: ...

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


class HouseholdOnboardingRepository(Protocol):
    async def get_by_user_id(self, user_id: UUID) -> StoredHousehold | None: ...

    async def create_for_user(self, user_id: UUID) -> StoredHousehold: ...

    async def reset_pending_onboarding(self, household_id: UUID) -> None: ...

    async def update_household_settings(
        self,
        household_id: UUID,
        settings: HouseholdSettingsInput,
    ) -> None: ...

    async def upsert_member(
        self,
        household_id: UUID,
        member: HouseholdMemberInput,
    ) -> None: ...

    async def add_or_update_pantry_item(
        self,
        household_id: UUID,
        ingredient_id: UUID,
        pantry_item: PantryItemInput,
    ) -> None: ...

    async def complete_onboarding(self, household_id: UUID, completed_at: datetime) -> None: ...


class IngredientCatalogRepository(Protocol):
    async def get_by_normalized_name(self, normalized_name: str) -> StoredIngredient | None: ...

    async def create(self, canonical_name: str, normalized_name: str) -> StoredIngredient: ...


@dataclass(frozen=True, slots=True)
class OnboardingRepositories:
    user_repository: UserOnboardingRepository
    household_repository: HouseholdOnboardingRepository
    ingredient_repository: IngredientCatalogRepository


OnboardingRepositoryBundleFactory = Callable[[AsyncSession], OnboardingRepositories]
