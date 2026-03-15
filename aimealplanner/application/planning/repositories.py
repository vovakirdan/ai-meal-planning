from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.planning.dto import (
    PlanDraftInput,
    PlanDraftResult,
    StoredDraftPlan,
    StoredPlanningHousehold,
    StoredPlanningUser,
)


class PlanningUserRepository(Protocol):
    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredPlanningUser | None: ...


class PlanningHouseholdRepository(Protocol):
    async def get_by_user_id(self, user_id: UUID) -> StoredPlanningHousehold | None: ...


class WeeklyPlanRepository(Protocol):
    async def get_latest_draft_for_household(
        self,
        household_id: UUID,
    ) -> StoredDraftPlan | None: ...

    async def delete_drafts_for_household(self, household_id: UUID) -> int: ...

    async def create_draft(
        self,
        household_id: UUID,
        timezone: str,
        active_slots: list[str],
        draft: PlanDraftInput,
    ) -> PlanDraftResult: ...


@dataclass(frozen=True, slots=True)
class PlanningRepositories:
    user_repository: PlanningUserRepository
    household_repository: PlanningHouseholdRepository
    weekly_plan_repository: WeeklyPlanRepository


PlanningRepositoryBundleFactory = Callable[[AsyncSession], PlanningRepositories]
