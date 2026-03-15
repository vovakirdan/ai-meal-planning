# ruff: noqa: RUF001
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
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
    DishQuickAction,
    GeneratedWeekPlan,
    HouseholdDishPolicyContext,
    PlanningMemberContext,
    PlanningPantryItemContext,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import (
    PlannedMealItemReplacement,
)
from aimealplanner.application.planning.repositories import PlanningRepositories
from aimealplanner.application.planning.shopping_dto import (
    ShoppingListItemDraft,
    ShoppingListResult,
    ShoppingSourceContext,
    ShoppingSourceIngredientEntry,
    ShoppingSourcePantryEntry,
)
from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    MealSlot,
    PlannedMealStatus,
    WeeklyPlanStatus,
)
from aimealplanner.infrastructure.db.models.dish import (
    DishIngredientRecord,
    DishRecipeRecord,
    DishRecord,
)
from aimealplanner.infrastructure.db.models.feedback import (
    DishFeedbackEventRecord,
    HouseholdDishPolicyRecord,
)
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
from aimealplanner.infrastructure.db.models.shopping import (
    ShoppingListItemRecord,
    ShoppingListRecord,
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
_WHITESPACE_PATTERN = re.compile(r"\s+")
_SHOPPING_LIST_DISPLAY_NAME_MAX_LENGTH = 255
_SHOPPING_LIST_QUANTITY_UNIT_MAX_LENGTH = 32
_SHOPPING_LIST_CATEGORY_MAX_LENGTH = 64


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

    async def list_members(self, household_id: UUID) -> list[StoredPlanningMember]:
        statement = (
            select(HouseholdMemberRecord)
            .where(HouseholdMemberRecord.household_id == household_id)
            .order_by(
                HouseholdMemberRecord.sort_order.asc(),
                HouseholdMemberRecord.created_at.asc(),
            )
        )
        members = list(await self._session.scalars(statement))
        return [
            StoredPlanningMember(
                id=member.id,
                household_id=member.household_id,
                display_name=member.display_name,
                sort_order=member.sort_order,
                is_active=member.is_active,
            )
            for member in members
        ]


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

    async def get_latest_confirmed_for_household(
        self,
        household_id: UUID,
    ) -> StoredPlanReference | None:
        statement = (
            select(WeeklyPlanRecord)
            .where(
                WeeklyPlanRecord.household_id == household_id,
                WeeklyPlanRecord.status == WeeklyPlanStatus.CONFIRMED,
            )
            .order_by(
                WeeklyPlanRecord.confirmed_at.desc(),
                WeeklyPlanRecord.created_at.desc(),
            )
            .limit(1)
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return StoredPlanReference(
            id=record.id,
            start_date=record.start_date,
            end_date=record.end_date,
            status=record.status,
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
                WeeklyPlanRecord.status.in_(
                    [WeeklyPlanStatus.DRAFT, WeeklyPlanStatus.CONFIRMED],
                ),
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
            status=record.status,
            start_date=record.start_date,
            end_date=record.end_date,
            days=[
                StoredPlanDaySummary(
                    meal_date=meal_date,
                    meals_count=len(day_meals),
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
                        for meal in sorted(day_meals, key=_sort_meal_record)
                    ],
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
            WeeklyPlanRecord.status.in_(
                [WeeklyPlanStatus.DRAFT, WeeklyPlanStatus.CONFIRMED],
            ),
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

        policy = None
        if item.dish_id is not None:
            policy_statement = select(HouseholdDishPolicyRecord).where(
                HouseholdDishPolicyRecord.household_id == household_id,
                HouseholdDishPolicyRecord.dish_id == item.dish_id,
            )
            policy = await self._session.scalar(policy_statement)

        summary = item.snapshot_payload.get("summary")
        if summary is not None and not isinstance(summary, str):
            summary = str(summary)

        return StoredPlanItemView(
            weekly_plan_id=item.planned_meal.weekly_plan_id,
            planned_meal_id=item.planned_meal_id,
            planned_meal_item_id=item.id,
            dish_id=item.dish_id,
            meal_date=item.planned_meal.meal_date,
            slot=item.planned_meal.slot.value,
            name=item.snapshot_name,
            summary=summary,
            adaptation_notes=list(item.adaptation_notes),
            snapshot_payload=dict(item.snapshot_payload),
            suggested_actions=_extract_suggested_actions(item.snapshot_payload),
            household_policy_verdict=policy.verdict if policy is not None else None,
            household_policy_note=policy.note if policy is not None else None,
        )

    async def update_item_snapshot(
        self,
        replacement: PlannedMealItemReplacement,
    ) -> None:
        statement = (
            select(PlannedMealItemRecord)
            .options(
                selectinload(PlannedMealItemRecord.planned_meal).selectinload(
                    PlannedMealRecord.weekly_plan,
                ),
            )
            .where(PlannedMealItemRecord.id == replacement.planned_meal_item_id)
        )
        record = await self._session.scalar(statement)
        if record is None:
            raise ValueError("Planned meal item not found")

        replacement_dish_id: UUID | None = None
        if (
            replacement.clear_dish_link
            and record.planned_meal.weekly_plan.status == WeeklyPlanStatus.CONFIRMED
        ):
            replacement_dish = await self._find_or_create_dish(
                replacement.name,
                replacement.snapshot_payload,
            )
            replacement_dish_id = replacement_dish.id

        record.snapshot_name = replacement.name
        record.snapshot_payload = replacement.snapshot_payload
        record.adaptation_notes = replacement.adaptation_notes
        if replacement.clear_dish_link:
            record.dish_id = replacement_dish_id
        await self._session.flush()

    async def ensure_item_dish(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID:
        _ = household_id
        statement = (
            select(PlannedMealItemRecord)
            .options(selectinload(PlannedMealItemRecord.dish))
            .where(PlannedMealItemRecord.id == planned_meal_item_id)
        )
        item = await self._session.scalar(statement)
        if item is None:
            raise ValueError("Planned meal item not found")

        if item.dish_id is not None:
            return item.dish_id

        dish = await self._find_or_create_dish_from_item(item)
        item.dish_id = dish.id
        await self._session.flush()
        return dish.id

    async def upsert_household_dish_policy(
        self,
        household_id: UUID,
        dish_id: UUID,
        verdict: DishFeedbackVerdict,
        note: str | None,
    ) -> None:
        statement = select(HouseholdDishPolicyRecord).where(
            HouseholdDishPolicyRecord.household_id == household_id,
            HouseholdDishPolicyRecord.dish_id == dish_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            self._session.add(
                HouseholdDishPolicyRecord(
                    household_id=household_id,
                    dish_id=dish_id,
                    verdict=verdict,
                    note=note,
                ),
            )
        else:
            record.verdict = verdict
            record.note = note
        await self._session.flush()

    async def delete_item(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID:
        statement = (
            select(PlannedMealItemRecord)
            .options(
                selectinload(PlannedMealItemRecord.planned_meal).selectinload(
                    PlannedMealRecord.weekly_plan,
                ),
            )
            .where(PlannedMealItemRecord.id == planned_meal_item_id)
        )
        record = await self._session.scalar(statement)
        if record is None or record.planned_meal.weekly_plan.household_id != household_id:
            raise ValueError("Planned meal item not found")

        planned_meal_id = record.planned_meal_id
        await self._session.delete(record)
        await self._session.flush()
        return planned_meal_id

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

    async def confirm_plan(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        confirmed_at: datetime,
    ) -> PlanConfirmationResult:
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
            )
        )
        record = await self._session.scalar(statement)
        if record is None:
            raise ValueError("Не удалось найти выбранный план.")
        if record.status != WeeklyPlanStatus.DRAFT:
            raise ValueError("Этот план уже подтвержден.")
        if not any(meal.items for meal in record.planned_meals):
            raise ValueError("Нельзя подтвердить пустой план недели.")

        for meal in record.planned_meals:
            for item in meal.items:
                if item.dish_id is not None:
                    continue
                dish = await self._find_or_create_dish_from_item(item)
                item.dish_id = dish.id
        await self._session.flush()

        record.status = WeeklyPlanStatus.CONFIRMED
        record.confirmed_at = confirmed_at
        await self._session.flush()
        return PlanConfirmationResult(
            weekly_plan_id=record.id,
            confirmed_at=confirmed_at,
        )

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
    ) -> None:
        member_statement = select(HouseholdMemberRecord.id).where(
            HouseholdMemberRecord.id == household_member_id,
            HouseholdMemberRecord.household_id == household_id,
            HouseholdMemberRecord.is_active.is_(True),
        )
        member_id = await self._session.scalar(member_statement)
        if member_id is None:
            raise ValueError("Не удалось найти выбранного участника семьи.")

        item_statement = (
            select(PlannedMealItemRecord)
            .options(
                selectinload(PlannedMealItemRecord.planned_meal).selectinload(
                    PlannedMealRecord.weekly_plan,
                ),
            )
            .where(PlannedMealItemRecord.id == planned_meal_item_id)
        )
        item = await self._session.scalar(item_statement)
        if item is None or item.planned_meal.weekly_plan.household_id != household_id:
            raise ValueError("Не удалось найти выбранное блюдо для отзыва.")

        event_statement = select(DishFeedbackEventRecord).where(
            DishFeedbackEventRecord.household_member_id == household_member_id,
            DishFeedbackEventRecord.planned_meal_item_id == planned_meal_item_id,
            DishFeedbackEventRecord.feedback_date == feedback_date,
        )
        event = await self._session.scalar(event_statement)
        if event is None:
            self._session.add(
                DishFeedbackEventRecord(
                    household_member_id=household_member_id,
                    dish_id=dish_id,
                    planned_meal_item_id=planned_meal_item_id,
                    feedback_date=feedback_date,
                    verdict=verdict,
                    raw_comment=raw_comment,
                    normalized_notes=normalized_notes,
                ),
            )
        else:
            event.dish_id = dish_id
            event.verdict = verdict
            event.raw_comment = raw_comment
            event.normalized_notes = normalized_notes
        await self._session.flush()

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
        feedback_statement = (
            select(DishFeedbackEventRecord, HouseholdMemberRecord, DishRecord)
            .join(
                HouseholdMemberRecord,
                DishFeedbackEventRecord.household_member_id == HouseholdMemberRecord.id,
            )
            .join(DishRecord, DishFeedbackEventRecord.dish_id == DishRecord.id)
            .where(HouseholdMemberRecord.household_id == household.id)
            .order_by(
                DishFeedbackEventRecord.feedback_date.desc(),
                DishFeedbackEventRecord.created_at.desc(),
            )
        )
        feedback_rows = list((await self._session.execute(feedback_statement)).all())
        policy_statement = (
            select(HouseholdDishPolicyRecord, DishRecord)
            .join(DishRecord, HouseholdDishPolicyRecord.dish_id == DishRecord.id)
            .where(HouseholdDishPolicyRecord.household_id == household.id)
            .order_by(HouseholdDishPolicyRecord.created_at.desc())
        )
        policy_rows = list((await self._session.execute(policy_statement)).all())
        feedback_notes_by_member_id: dict[UUID, list[str]] = {}
        for feedback_event, member, dish in feedback_rows:
            member_notes = feedback_notes_by_member_id.setdefault(member.id, [])
            if len(member_notes) >= 5:
                continue
            memory_entry = _build_feedback_memory_entry(
                dish_name=dish.canonical_name,
                feedback_event=feedback_event,
            )
            if memory_entry is None:
                continue
            member_notes.append(memory_entry)

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
                    feedback_notes=feedback_notes_by_member_id.get(member.id, []),
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
            household_policies=[
                HouseholdDishPolicyContext(
                    dish_name=dish.canonical_name,
                    verdict=policy.verdict,
                    note=policy.note,
                )
                for policy, dish in policy_rows
            ],
        )

    async def get_shopping_source(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> ShoppingSourceContext | None:
        plan_statement = (
            select(WeeklyPlanRecord)
            .options(
                selectinload(WeeklyPlanRecord.planned_meals).selectinload(
                    PlannedMealRecord.items,
                ),
            )
            .where(
                WeeklyPlanRecord.id == weekly_plan_id,
                WeeklyPlanRecord.household_id == household_id,
                WeeklyPlanRecord.status.in_(
                    [WeeklyPlanStatus.DRAFT, WeeklyPlanStatus.CONFIRMED],
                ),
            )
        )
        plan = await self._session.scalar(plan_statement)
        if plan is None:
            return None

        for meal in plan.planned_meals:
            for item in meal.items:
                if item.dish_id is not None:
                    continue
                if _extract_snapshot_ingredients(item.snapshot_payload):
                    continue
                dish = await self._find_or_create_dish_from_item(item)
                item.dish_id = dish.id
        await self._session.flush()

        refreshed_plan_statement = (
            select(WeeklyPlanRecord)
            .options(
                selectinload(WeeklyPlanRecord.planned_meals)
                .selectinload(PlannedMealRecord.items)
                .selectinload(PlannedMealItemRecord.dish)
                .selectinload(DishRecord.ingredients)
                .selectinload(DishIngredientRecord.ingredient),
            )
            .where(
                WeeklyPlanRecord.id == weekly_plan_id,
                WeeklyPlanRecord.household_id == household_id,
            )
        )
        refreshed_plan = await self._session.scalar(refreshed_plan_statement)
        if refreshed_plan is None:
            return None

        pantry_statement = (
            select(PantryItemRecord)
            .options(selectinload(PantryItemRecord.ingredient))
            .where(PantryItemRecord.household_id == household_id)
        )
        pantry_items = list(await self._session.scalars(pantry_statement))

        ingredient_entries: list[ShoppingSourceIngredientEntry] = []
        for meal in refreshed_plan.planned_meals:
            for item in meal.items:
                snapshot_entries = await self._build_snapshot_shopping_entries(item)
                if snapshot_entries:
                    ingredient_entries.extend(snapshot_entries)
                    continue
                dish = item.dish
                if dish is None:
                    continue
                for dish_ingredient in dish.ingredients:
                    ingredient_entries.append(
                        ShoppingSourceIngredientEntry(
                            ingredient_id=dish_ingredient.ingredient_id,
                            canonical_name=dish_ingredient.ingredient.canonical_name,
                            shopping_category=dish_ingredient.ingredient.shopping_category,
                            default_unit=dish_ingredient.ingredient.default_unit,
                            amount_text=_extract_amount_text(dish_ingredient),
                            quantity_value=dish_ingredient.quantity_value,
                            quantity_unit=dish_ingredient.quantity_unit,
                            preparation_note=dish_ingredient.preparation_note,
                            dish_name=item.snapshot_name,
                        ),
                    )

        return ShoppingSourceContext(
            weekly_plan_id=refreshed_plan.id,
            start_date=refreshed_plan.start_date,
            end_date=refreshed_plan.end_date,
            ingredient_entries=ingredient_entries,
            pantry_entries=[
                ShoppingSourcePantryEntry(
                    ingredient_id=pantry_item.ingredient_id,
                    stock_level=pantry_item.stock_level,
                    quantity_value=pantry_item.quantity_value,
                    quantity_unit=pantry_item.quantity_unit,
                    note=pantry_item.note,
                )
                for pantry_item in pantry_items
            ],
        )

    async def create_shopping_list(
        self,
        weekly_plan_id: UUID,
        items: list[ShoppingListItemDraft],
    ) -> ShoppingListResult:
        plan = await self._session.get(WeeklyPlanRecord, weekly_plan_id)
        if plan is None:
            raise ValueError("Weekly plan not found")

        version_statement = select(func.max(ShoppingListRecord.version)).where(
            ShoppingListRecord.weekly_plan_id == weekly_plan_id,
        )
        latest_version = await self._session.scalar(version_statement)
        next_version = (latest_version or 0) + 1

        record = ShoppingListRecord(
            weekly_plan_id=weekly_plan_id,
            version=next_version,
        )
        self._session.add(record)
        await self._session.flush()

        for position, item in enumerate(items):
            quantity_value, quantity_unit = _normalize_shopping_storage_quantity(
                item.quantity_value,
                item.quantity_unit,
            )
            self._session.add(
                ShoppingListItemRecord(
                    shopping_list_id=record.id,
                    ingredient_id=item.ingredient_id,
                    position=position,
                    display_name=item.display_name[:_SHOPPING_LIST_DISPLAY_NAME_MAX_LENGTH],
                    quantity_value=quantity_value,
                    quantity_unit=quantity_unit,
                    category=_truncate_optional_value(
                        item.category,
                        _SHOPPING_LIST_CATEGORY_MAX_LENGTH,
                    ),
                    availability_status=item.availability_status,
                    note=_merge_shopping_item_note(item),
                ),
            )

        await self._session.flush()
        return ShoppingListResult(
            shopping_list_id=record.id,
            weekly_plan_id=weekly_plan_id,
            version=next_version,
            start_date=plan.start_date,
            end_date=plan.end_date,
            items=items,
        )

    async def _build_snapshot_shopping_entries(
        self,
        item: PlannedMealItemRecord,
    ) -> list[ShoppingSourceIngredientEntry]:
        entries: list[ShoppingSourceIngredientEntry] = []
        for ingredient_payload in _extract_snapshot_ingredients(item.snapshot_payload):
            ingredient = await self._get_or_create_ingredient(ingredient_payload["name"])
            entries.append(
                ShoppingSourceIngredientEntry(
                    ingredient_id=ingredient.id,
                    canonical_name=ingredient.canonical_name,
                    shopping_category=ingredient.shopping_category,
                    default_unit=ingredient.default_unit,
                    amount_text=ingredient_payload.get("amount"),
                    quantity_value=None,
                    quantity_unit=None,
                    preparation_note=ingredient_payload.get("preparation_note"),
                    dish_name=item.snapshot_name,
                ),
            )
        return entries

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
                            "suggested_actions": [
                                {
                                    "label": action.label,
                                    "instruction": action.instruction,
                                }
                                for action in item.suggested_actions
                            ],
                        },
                        adaptation_notes=item.adaptation_notes,
                    ),
                )
        await self._session.flush()

    async def _find_or_create_dish_from_item(self, item: PlannedMealItemRecord) -> DishRecord:
        return await self._find_or_create_dish(item.snapshot_name, item.snapshot_payload)

    async def _find_or_create_dish(
        self,
        snapshot_name: str,
        snapshot_payload: dict[str, Any],
    ) -> DishRecord:
        normalized_name = _normalize_name(snapshot_name)
        canonical_key = _build_dish_canonical_key(snapshot_name, snapshot_payload)

        dish_statement = None
        if canonical_key is not None:
            dish_statement = select(DishRecord).where(DishRecord.canonical_key == canonical_key)
        else:
            dish_statement = select(DishRecord).where(DishRecord.normalized_name == normalized_name)

        dish = await self._session.scalar(dish_statement)
        if dish is not None:
            return dish

        summary_value = snapshot_payload.get("summary")
        summary = summary_value.strip() if isinstance(summary_value, str) else None
        dish = DishRecord(
            canonical_name=snapshot_name,
            normalized_name=normalized_name,
            canonical_key=canonical_key,
            summary=summary,
        )
        self._session.add(dish)
        await self._session.flush()

        recipe = _build_recipe_record(dish.id, snapshot_payload)
        if recipe is not None:
            self._session.add(recipe)

        snapshot_ingredients = _extract_snapshot_ingredients(snapshot_payload)
        for position, ingredient_payload in enumerate(snapshot_ingredients):
            ingredient_name = ingredient_payload["name"]
            ingredient = await self._get_or_create_ingredient(ingredient_name)
            self._session.add(
                DishIngredientRecord(
                    dish_id=dish.id,
                    ingredient_id=ingredient.id,
                    position=position,
                    quantity_unit=ingredient_payload.get("amount"),
                    preparation_note=ingredient_payload.get("preparation_note"),
                    metadata_json=dict(ingredient_payload),
                ),
            )
        await self._session.flush()
        return dish

    async def _get_or_create_ingredient(self, ingredient_name: str) -> IngredientRecord:
        normalized_name = _normalize_name(ingredient_name)
        statement = select(IngredientRecord).where(
            IngredientRecord.normalized_name == normalized_name,
        )
        ingredient = await self._session.scalar(statement)
        if ingredient is not None:
            return ingredient

        ingredient = IngredientRecord(
            canonical_name=ingredient_name,
            normalized_name=normalized_name,
        )
        self._session.add(ingredient)
        await self._session.flush()
        return ingredient


def build_planning_repositories(session: AsyncSession) -> PlanningRepositories:
    return PlanningRepositories(
        user_repository=SqlAlchemyPlanningUserRepository(session),
        household_repository=SqlAlchemyPlanningHouseholdRepository(session),
        weekly_plan_repository=SqlAlchemyWeeklyPlanRepository(session),
    )


def _sort_meal_record(meal: PlannedMealRecord) -> tuple[int, str]:
    return (_MEAL_SLOT_ORDER.get(meal.slot.value, 999), meal.slot.value)


def _normalize_name(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value.strip()).lower()


def _build_dish_canonical_key(snapshot_name: str, snapshot_payload: dict[str, Any]) -> str | None:
    normalized_name = _normalize_name(snapshot_name)
    ingredient_names = [
        _normalize_name(ingredient["name"])
        for ingredient in _extract_snapshot_ingredients(snapshot_payload)
    ]
    if ingredient_names:
        joined_ingredients = "|".join(ingredient_names[:4])
        return f"{normalized_name}::{joined_ingredients}"[:255]
    if normalized_name:
        return normalized_name[:255]
    return None


def _extract_snapshot_ingredients(snapshot_payload: dict[str, Any]) -> list[dict[str, str]]:
    payload = snapshot_payload.get("ingredients")
    if not isinstance(payload, list):
        return []

    ingredients: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        name_value = raw_item.get("name")
        if not isinstance(name_value, str) or not name_value.strip():
            continue
        normalized_name = _normalize_name(name_value)
        if normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        ingredient_payload: dict[str, str] = {"name": name_value.strip()}
        amount_value = raw_item.get("amount")
        if isinstance(amount_value, str) and amount_value.strip():
            ingredient_payload["amount"] = amount_value.strip()
        preparation_note = raw_item.get("preparation_note")
        if isinstance(preparation_note, str) and preparation_note.strip():
            ingredient_payload["preparation_note"] = preparation_note.strip()
        ingredients.append(ingredient_payload)
    return ingredients


def _extract_amount_text(dish_ingredient: DishIngredientRecord) -> str | None:
    metadata_amount = dish_ingredient.metadata_json.get("amount")
    if isinstance(metadata_amount, str) and metadata_amount.strip():
        return metadata_amount.strip()
    if dish_ingredient.quantity_value is not None and dish_ingredient.quantity_unit:
        return f"{dish_ingredient.quantity_value} {dish_ingredient.quantity_unit}".strip()
    if dish_ingredient.quantity_unit:
        return dish_ingredient.quantity_unit.strip()
    return None


def _merge_shopping_item_note(item: ShoppingListItemDraft) -> str | None:
    if item.note is None:
        return None
    if item.quantity_label is None:
        return item.note
    return f"Итог: {item.quantity_label}. {item.note}"


def _normalize_shopping_storage_quantity(
    quantity_value: Decimal | None,
    quantity_unit: str | None,
) -> tuple[Decimal | None, str | None]:
    if quantity_unit is None:
        return quantity_value, None
    normalized_unit = quantity_unit.strip()
    if not normalized_unit:
        return quantity_value, None
    if len(normalized_unit) > _SHOPPING_LIST_QUANTITY_UNIT_MAX_LENGTH:
        return None, None
    return quantity_value, normalized_unit


def _truncate_optional_value(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    return normalized_value[:max_length]


def _extract_suggested_actions(snapshot_payload: dict[str, Any]) -> list[DishQuickAction]:
    payload = snapshot_payload.get("suggested_actions")
    if not isinstance(payload, list):
        return []

    actions: list[DishQuickAction] = []
    seen_labels: set[str] = set()
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        label = raw_item.get("label")
        instruction = raw_item.get("instruction")
        if not isinstance(label, str) or not isinstance(instruction, str):
            continue
        normalized_label = label.strip().casefold()
        if not normalized_label or not instruction.strip() or normalized_label in seen_labels:
            continue
        seen_labels.add(normalized_label)
        actions.append(
            DishQuickAction(
                label=label.strip(),
                instruction=instruction.strip(),
            ),
        )
    return actions[:2]


def _build_recipe_record(
    dish_id: UUID,
    snapshot_payload: dict[str, Any],
) -> DishRecipeRecord | None:
    preparation_steps = _extract_step_list(snapshot_payload.get("preparation_steps"))
    cooking_steps = _extract_step_list(snapshot_payload.get("cooking_steps"))
    serving_steps = _extract_step_list(snapshot_payload.get("serving_steps"))
    serving_notes = snapshot_payload.get("serving_notes")
    prep_time_minutes = _coerce_optional_int(snapshot_payload.get("prep_time_minutes"))
    cook_time_minutes = _coerce_optional_int(snapshot_payload.get("cook_time_minutes"))

    if (
        not preparation_steps
        and not cooking_steps
        and not serving_steps
        and not isinstance(serving_notes, str)
        and prep_time_minutes is None
        and cook_time_minutes is None
    ):
        return None

    return DishRecipeRecord(
        dish_id=dish_id,
        preparation_steps=preparation_steps,
        cooking_steps=cooking_steps,
        serving_steps=serving_steps,
        prep_time_minutes=prep_time_minutes,
        cook_time_minutes=cook_time_minutes,
        serving_notes=serving_notes.strip() if isinstance(serving_notes, str) else None,
    )


def _extract_step_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [step.strip() for step in value if isinstance(step, str) and step.strip()]


def _coerce_optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _build_feedback_memory_entry(
    *,
    dish_name: str,
    feedback_event: DishFeedbackEventRecord,
) -> str | None:
    planning_note = feedback_event.normalized_notes.get("planning_note")
    if isinstance(planning_note, str) and planning_note.strip():
        note_text = planning_note.strip()
    elif isinstance(feedback_event.raw_comment, str) and feedback_event.raw_comment.strip():
        note_text = feedback_event.raw_comment.strip()
    else:
        note_text = _render_feedback_verdict_hint(feedback_event.verdict)

    if not note_text:
        return None

    restriction_candidate = feedback_event.normalized_notes.get("restriction_candidate")
    if isinstance(restriction_candidate, str) and restriction_candidate.strip():
        return (
            f"{dish_name}: {note_text}. Возможное новое ограничение: "
            f"{restriction_candidate.strip()}."
        )
    return f"{dish_name}: {note_text}."


def _render_feedback_verdict_hint(verdict: DishFeedbackVerdict) -> str:
    labels = {
        DishFeedbackVerdict.FAVORITE: "очень понравилось",
        DishFeedbackVerdict.CAN_REPEAT: "можно повторять",
        DishFeedbackVerdict.RARELY_REPEAT: "лучше повторять редко",
        DishFeedbackVerdict.NEVER_AGAIN: "лучше больше не повторять",
    }
    return labels.get(verdict, verdict.value)
