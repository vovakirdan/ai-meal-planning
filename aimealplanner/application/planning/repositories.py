from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDayView,
    StoredPlanItemView,
    StoredPlanMealView,
    StoredPlanOverview,
)
from aimealplanner.application.planning.dto import (
    PlanDraftInput,
    PlanDraftResult,
    StoredDraftPlan,
    StoredPlanningHousehold,
    StoredPlanningUser,
)
from aimealplanner.application.planning.generation_dto import (
    GeneratedWeekPlan,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import (
    PlannedMealItemReplacement,
)
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict


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

    async def get_plan_overview(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> StoredPlanOverview | None: ...

    async def get_day_view(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> StoredPlanDayView | None: ...

    async def get_meal_view(
        self,
        household_id: UUID,
        planned_meal_id: UUID,
    ) -> StoredPlanMealView | None: ...

    async def get_item_view(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> StoredPlanItemView | None: ...

    async def update_item_snapshot(
        self,
        replacement: PlannedMealItemReplacement,
    ) -> None: ...

    async def ensure_item_dish(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID: ...

    async def upsert_household_dish_policy(
        self,
        household_id: UUID,
        dish_id: UUID,
        verdict: DishFeedbackVerdict,
        note: str | None,
    ) -> None: ...

    async def delete_item(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID: ...

    async def get_generation_context(
        self,
        weekly_plan_id: UUID,
    ) -> WeeklyPlanGenerationContext | None: ...

    async def replace_generated_meals(
        self,
        weekly_plan_id: UUID,
        generated_plan: GeneratedWeekPlan,
    ) -> None: ...

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
