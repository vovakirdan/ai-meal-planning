from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aimealplanner.application.planning.browsing_dto import (
    StoredMealItemSummary,
    StoredPlanDaySummary,
    StoredPlanDayView,
    StoredPlanItemView,
    StoredPlanMealSummary,
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
    PlanningMemberContext,
    PlanningPantryItemContext,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.repositories import PlanningRepositories
from aimealplanner.infrastructure.db.enums import MealSlot, PlannedMealStatus, WeeklyPlanStatus
from aimealplanner.infrastructure.db.models.household import (
    HouseholdMemberRecord,
    HouseholdRecord,
    PantryItemRecord,
)
from aimealplanner.infrastructure.db.models.ingredient import IngredientRecord
from aimealplanner.infrastructure.db.models.plan import (
    PlannedMealItemRecord,
    PlannedMealRecord,
    WeeklyPlanRecord,
)
from aimealplanner.infrastructure.db.models.user import UserRecord

_MEAL_SLOT_ORDER = {
    MealSlot.BREAKFAST.value: 0,
    MealSlot.LUNCH.value: 1,
    MealSlot.DINNER.value: 2,
    MealSlot.SNACK_1.value: 3,
    MealSlot.SNACK_2.value: 4,
    MealSlot.DESSERT.value: 5,
}


class SqlAlchemyPlanningUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredPlanningUser | None:
        statement = select(UserRecord).where(UserRecord.telegram_user_id == telegram_user_id)
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return StoredPlanningUser(
            id=record.id,
            telegram_user_id=record.telegram_user_id,
            timezone=record.timezone,
        )


class SqlAlchemyPlanningHouseholdRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> StoredPlanningHousehold | None:
        household_statement = select(HouseholdRecord).where(HouseholdRecord.user_id == user_id)
        household = await self._session.scalar(household_statement)
        if household is None:
            return None

        pantry_count_statement = select(func.count(PantryItemRecord.id)).where(
            PantryItemRecord.household_id == household.id,
        )
        pantry_items_count = await self._session.scalar(pantry_count_statement)
        return StoredPlanningHousehold(
            id=household.id,
            user_id=household.user_id,
            onboarding_completed_at=household.onboarding_completed_at,
            default_meal_count_per_day=household.default_meal_count_per_day,
            desserts_enabled=household.desserts_enabled,
            repeatability_mode=household.repeatability_mode,
            pantry_items_count=pantry_items_count or 0,
        )


class SqlAlchemyWeeklyPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_draft_for_household(self, household_id: UUID) -> StoredDraftPlan | None:
        statement = (
            select(WeeklyPlanRecord)
            .where(
                WeeklyPlanRecord.household_id == household_id,
                WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
            )
            .order_by(WeeklyPlanRecord.created_at.desc())
            .limit(1)
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return StoredDraftPlan(
            id=record.id,
            start_date=record.start_date,
            end_date=record.end_date,
        )

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        count_statement = select(func.count(WeeklyPlanRecord.id)).where(
            WeeklyPlanRecord.household_id == household_id,
            WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
        )
        existing_draft_count = await self._session.scalar(count_statement)
        delete_statement = delete(WeeklyPlanRecord).where(
            WeeklyPlanRecord.household_id == household_id,
            WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
        )
        await self._session.execute(delete_statement)
        return existing_draft_count or 0

    async def get_plan_overview(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> StoredPlanOverview | None:
        statement = (
            select(WeeklyPlanRecord)
            .options(
                selectinload(WeeklyPlanRecord.planned_meals).selectinload(
                    PlannedMealRecord.items,
                ),
            )
            .where(
                WeeklyPlanRecord.id == weekly_plan_id,
                WeeklyPlanRecord.household_id == household_id,
                WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
            )
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None

        meals_by_day: dict[date, list[PlannedMealRecord]] = {}
        for meal in record.planned_meals:
            meals_by_day.setdefault(meal.meal_date, []).append(meal)

        return StoredPlanOverview(
            weekly_plan_id=record.id,
            start_date=record.start_date,
            end_date=record.end_date,
            days=[
                StoredPlanDaySummary(
                    meal_date=meal_date,
                    meals_count=len(day_meals),
                )
                for meal_date, day_meals in sorted(meals_by_day.items())
            ],
        )

    async def get_day_view(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> StoredPlanDayView | None:
        plan_statement = select(WeeklyPlanRecord.id).where(
            WeeklyPlanRecord.id == weekly_plan_id,
            WeeklyPlanRecord.household_id == household_id,
            WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
        )
        plan_id = await self._session.scalar(plan_statement)
        if plan_id is None:
            return None

        statement = (
            select(PlannedMealRecord)
            .options(selectinload(PlannedMealRecord.items))
            .where(
                PlannedMealRecord.weekly_plan_id == weekly_plan_id,
                PlannedMealRecord.meal_date == meal_date,
            )
        )
        meals = list(await self._session.scalars(statement))

        return StoredPlanDayView(
            weekly_plan_id=weekly_plan_id,
            meal_date=meal_date,
            meals=[
                StoredPlanMealSummary(
                    planned_meal_id=meal.id,
                    slot=meal.slot.value,
                    note=meal.note,
                    item_names=[
                        item.snapshot_name
                        for item in sorted(meal.items, key=lambda item: item.position)
                    ],
                )
                for meal in sorted(meals, key=_sort_meal_record)
            ],
        )

    async def get_meal_view(
        self,
        household_id: UUID,
        planned_meal_id: UUID,
    ) -> StoredPlanMealView | None:
        statement = (
            select(PlannedMealRecord)
            .options(
                selectinload(PlannedMealRecord.items),
                selectinload(PlannedMealRecord.weekly_plan),
            )
            .where(PlannedMealRecord.id == planned_meal_id)
        )
        meal = await self._session.scalar(statement)
        if meal is None or meal.weekly_plan.household_id != household_id:
            return None

        return StoredPlanMealView(
            weekly_plan_id=meal.weekly_plan_id,
            planned_meal_id=meal.id,
            meal_date=meal.meal_date,
            slot=meal.slot.value,
            note=meal.note,
            items=[
                StoredMealItemSummary(
                    planned_meal_item_id=item.id,
                    position=item.position,
                    name=item.snapshot_name,
                )
                for item in sorted(meal.items, key=lambda item: item.position)
            ],
        )

    async def get_item_view(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> StoredPlanItemView | None:
        statement = (
            select(PlannedMealItemRecord)
            .options(
                selectinload(PlannedMealItemRecord.planned_meal).selectinload(
                    PlannedMealRecord.weekly_plan,
                ),
            )
            .where(PlannedMealItemRecord.id == planned_meal_item_id)
        )
        item = await self._session.scalar(statement)
        if item is None or item.planned_meal.weekly_plan.household_id != household_id:
            return None

        summary = item.snapshot_payload.get("summary")
        if summary is not None and not isinstance(summary, str):
            summary = str(summary)

        return StoredPlanItemView(
            weekly_plan_id=item.planned_meal.weekly_plan_id,
            planned_meal_id=item.planned_meal_id,
            planned_meal_item_id=item.id,
            meal_date=item.planned_meal.meal_date,
            slot=item.planned_meal.slot.value,
            name=item.snapshot_name,
            summary=summary,
            adaptation_notes=list(item.adaptation_notes),
            snapshot_payload=dict(item.snapshot_payload),
        )

    async def create_draft(
        self,
        household_id: UUID,
        timezone: str,
        active_slots: list[str],
        draft: PlanDraftInput,
    ) -> PlanDraftResult:
        record = WeeklyPlanRecord(
            household_id=household_id,
            start_date=draft.start_date,
            end_date=draft.end_date,
            timezone=timezone,
            meal_count_per_day=draft.meal_count_per_day,
            desserts_enabled=draft.desserts_enabled,
            active_slots=active_slots,
            week_mood=draft.week_mood,
            weekly_notes=draft.weekly_notes,
            pantry_considered=draft.pantry_considered,
            context_payload=draft.context_payload,
        )
        self._session.add(record)
        await self._session.flush()
        return PlanDraftResult(
            weekly_plan_id=record.id,
            start_date=record.start_date,
            end_date=record.end_date,
            active_slots=list(record.active_slots),
            pantry_considered=record.pantry_considered,
        )

    async def get_generation_context(
        self,
        weekly_plan_id: UUID,
    ) -> WeeklyPlanGenerationContext | None:
        weekly_plan = await self._session.get(WeeklyPlanRecord, weekly_plan_id)
        if weekly_plan is None:
            return None

        household = await self._session.get(HouseholdRecord, weekly_plan.household_id)
        if household is None:
            return None

        members_statement = (
            select(HouseholdMemberRecord)
            .where(
                HouseholdMemberRecord.household_id == household.id,
                HouseholdMemberRecord.is_active.is_(True),
            )
            .order_by(HouseholdMemberRecord.sort_order.asc())
        )
        members = list(await self._session.scalars(members_statement))

        pantry_statement = (
            select(PantryItemRecord, IngredientRecord)
            .join(IngredientRecord, PantryItemRecord.ingredient_id == IngredientRecord.id)
            .where(PantryItemRecord.household_id == household.id)
            .order_by(IngredientRecord.canonical_name.asc())
        )
        pantry_rows = list((await self._session.execute(pantry_statement)).all())

        return WeeklyPlanGenerationContext(
            weekly_plan_id=weekly_plan.id,
            household_id=household.id,
            timezone=weekly_plan.timezone,
            start_date=weekly_plan.start_date,
            end_date=weekly_plan.end_date,
            meal_count_per_day=weekly_plan.meal_count_per_day,
            desserts_enabled=weekly_plan.desserts_enabled,
            repeatability_mode=household.repeatability_mode,
            active_slots=list(weekly_plan.active_slots),
            week_mood=weekly_plan.week_mood,
            weekly_notes=weekly_plan.weekly_notes,
            pantry_considered=weekly_plan.pantry_considered,
            context_payload=dict(weekly_plan.context_payload),
            members=[
                PlanningMemberContext(
                    display_name=member.display_name,
                    constraints=list(member.constraints),
                    favorite_cuisines=list(member.favorite_cuisines),
                    profile_note=member.profile_note,
                )
                for member in members
            ],
            pantry_items=[
                PlanningPantryItemContext(
                    ingredient_name=ingredient.canonical_name,
                    stock_level=pantry_item.stock_level,
                    quantity_value=pantry_item.quantity_value,
                    quantity_unit=pantry_item.quantity_unit,
                    note=pantry_item.note,
                )
                for pantry_item, ingredient in pantry_rows
            ],
        )

    async def replace_generated_meals(
        self,
        weekly_plan_id: UUID,
        generated_plan: GeneratedWeekPlan,
    ) -> None:
        delete_statement = delete(PlannedMealRecord).where(
            PlannedMealRecord.weekly_plan_id == weekly_plan_id,
        )
        await self._session.execute(delete_statement)

        for meal in generated_plan.meals:
            planned_meal = PlannedMealRecord(
                weekly_plan_id=weekly_plan_id,
                meal_date=meal.meal_date,
                slot=MealSlot(meal.slot),
                status=PlannedMealStatus.PLANNED,
                note=meal.note,
            )
            self._session.add(planned_meal)
            await self._session.flush()

            for index, item in enumerate(meal.items):
                self._session.add(
                    PlannedMealItemRecord(
                        planned_meal_id=planned_meal.id,
                        position=index,
                        snapshot_name=item.name,
                        snapshot_payload={
                            "summary": item.summary,
                            "generation_source": "weekly_plan_ai",
                        },
                        adaptation_notes=item.adaptation_notes,
                    ),
                )
        await self._session.flush()


def build_planning_repositories(session: AsyncSession) -> PlanningRepositories:
    return PlanningRepositories(
        user_repository=SqlAlchemyPlanningUserRepository(session),
        household_repository=SqlAlchemyPlanningHouseholdRepository(session),
        weekly_plan_repository=SqlAlchemyWeeklyPlanRepository(session),
    )


def _sort_meal_record(meal: PlannedMealRecord) -> tuple[int, str]:
    return (_MEAL_SLOT_ORDER.get(meal.slot.value, 999), meal.slot.value)
