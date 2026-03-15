from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
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
    PlanConfirmationResult,
    PlanDraftInput,
    PlanDraftResult,
    StoredDraftPlan,
    StoredPlanningHousehold,
    StoredPlanningMember,
    StoredPlanningUser,
    StoredPlanReference,
)
from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedWeekPlan,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import (
    PlannedMealItemReplacement,
)
from aimealplanner.application.planning.shopping_dto import (
    ShoppingListItemDraft,
    ShoppingListResult,
    ShoppingSourceContext,
)
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict


class PlanningUserRepository(Protocol):
    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredPlanningUser | None: ...


class PlanningHouseholdRepository(Protocol):
    async def get_by_user_id(self, user_id: UUID) -> StoredPlanningHousehold | None: ...

    async def list_members(self, household_id: UUID) -> list[StoredPlanningMember]: ...


class WeeklyPlanRepository(Protocol):
    async def get_latest_draft_for_household(
        self,
        household_id: UUID,
    ) -> StoredDraftPlan | None: ...

    async def get_latest_confirmed_for_household(
        self,
        household_id: UUID,
    ) -> StoredPlanReference | None: ...

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

    async def replace_meal_with_generated(
        self,
        household_id: UUID,
        planned_meal_id: UUID,
        generated_meal: GeneratedMeal,
    ) -> None: ...

    async def replace_day_with_generated(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
        generated_plan: GeneratedWeekPlan,
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

    async def confirm_plan(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        confirmed_at: datetime,
    ) -> PlanConfirmationResult: ...

    async def upsert_feedback_event(
        self,
        household_id: UUID,
        household_member_id: UUID,
        planned_meal_item_id: UUID,
        dish_id: UUID,
        feedback_date: date,
        verdict: DishFeedbackVerdict,
        raw_comment: str | None,
        normalized_notes: dict[str, object],
    ) -> None: ...

    async def get_shopping_source(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> ShoppingSourceContext | None: ...

    async def create_shopping_list(
        self,
        weekly_plan_id: UUID,
        items: list[ShoppingListItemDraft],
    ) -> ShoppingListResult: ...


@dataclass(frozen=True, slots=True)
class PlanningRepositories:
    user_repository: PlanningUserRepository
    household_repository: PlanningHouseholdRepository
    weekly_plan_repository: WeeklyPlanRepository


PlanningRepositoryBundleFactory = Callable[[AsyncSession], PlanningRepositories]
