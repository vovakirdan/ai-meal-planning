# ruff: noqa: RUF001
from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
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
from aimealplanner.infrastructure.db.models.dish import DishRecord
from aimealplanner.infrastructure.db.models.feedback import HouseholdDishPolicyRecord
from aimealplanner.infrastructure.db.models.household import (
    HouseholdMemberRecord,
    HouseholdRecord,
    PantryItemRecord,
)
from aimealplanner.infrastructure.db.models.ingredient import IngredientRecord
from aimealplanner.infrastructure.db.models.user import UserRecord


def _to_user(record: UserRecord) -> StoredSettingsUser:
    return StoredSettingsUser(
        id=record.id,
        telegram_user_id=record.telegram_user_id,
        timezone=record.timezone,
        daily_feedback_reminder_enabled=record.daily_feedback_reminder_enabled,
        daily_feedback_reminder_time=record.daily_feedback_reminder_time,
        weekly_planning_reminder_enabled=record.weekly_planning_reminder_enabled,
        weekly_planning_reminder_day_of_week=record.weekly_planning_reminder_day_of_week,
        weekly_planning_reminder_time=record.weekly_planning_reminder_time,
    )


def _to_household(record: HouseholdRecord) -> StoredSettingsHousehold:
    return StoredSettingsHousehold(
        id=record.id,
        user_id=record.user_id,
        onboarding_completed_at=record.onboarding_completed_at,
        default_meal_count_per_day=record.default_meal_count_per_day,
        desserts_enabled=record.desserts_enabled,
        repeatability_mode=record.repeatability_mode,
    )


def _to_member(record: HouseholdMemberRecord) -> StoredSettingsMember:
    return StoredSettingsMember(
        id=record.id,
        household_id=record.household_id,
        display_name=record.display_name,
        sort_order=record.sort_order,
        constraints=list(record.constraints),
        favorite_cuisines=list(record.favorite_cuisines),
        profile_note=record.profile_note,
        is_active=record.is_active,
    )


def _to_pantry_item(
    pantry_item: PantryItemRecord,
    ingredient: IngredientRecord,
) -> StoredSettingsPantryItem:
    return StoredSettingsPantryItem(
        id=pantry_item.id,
        ingredient_id=pantry_item.ingredient_id,
        ingredient_name=ingredient.canonical_name,
        stock_level=pantry_item.stock_level,
        quantity_value=pantry_item.quantity_value,
        quantity_unit=pantry_item.quantity_unit,
        note=pantry_item.note,
    )


def _to_dish_policy(
    policy: HouseholdDishPolicyRecord,
    dish: DishRecord,
) -> StoredSettingsDishPolicy:
    return StoredSettingsDishPolicy(
        id=policy.id,
        dish_id=policy.dish_id,
        dish_name=dish.canonical_name,
        verdict=policy.verdict,
        note=policy.note,
    )


class SqlAlchemySettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> StoredSettingsUser | None:
        statement = select(UserRecord).where(UserRecord.telegram_user_id == telegram_user_id)
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return _to_user(record)

    async def get_household_by_user_id(
        self,
        user_id: UUID,
    ) -> StoredSettingsHousehold | None:
        statement = select(HouseholdRecord).where(HouseholdRecord.user_id == user_id)
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return _to_household(record)

    async def update_household_planning_settings(
        self,
        household_id: UUID,
        *,
        meal_count_per_day: int,
        desserts_enabled: bool,
        repeatability_mode: RepeatabilityMode,
    ) -> None:
        record = await self._get_required_household(household_id)
        record.default_meal_count_per_day = meal_count_per_day
        record.desserts_enabled = desserts_enabled
        record.repeatability_mode = repeatability_mode

    async def update_daily_feedback_reminder(
        self,
        user_id: UUID,
        reminder_time: time | None,
    ) -> None:
        record = await self._get_required_user(user_id)
        record.daily_feedback_reminder_enabled = reminder_time is not None
        record.daily_feedback_reminder_time = reminder_time

    async def update_weekly_planning_reminder(
        self,
        user_id: UUID,
        day_of_week: int | None,
        reminder_time: time | None,
    ) -> None:
        record = await self._get_required_user(user_id)
        is_enabled = day_of_week is not None and reminder_time is not None
        record.weekly_planning_reminder_enabled = is_enabled
        record.weekly_planning_reminder_day_of_week = day_of_week if is_enabled else None
        record.weekly_planning_reminder_time = reminder_time if is_enabled else None

    async def list_members(self, household_id: UUID) -> list[StoredSettingsMember]:
        statement = (
            select(HouseholdMemberRecord)
            .where(HouseholdMemberRecord.household_id == household_id)
            .order_by(
                HouseholdMemberRecord.is_active.desc(),
                HouseholdMemberRecord.sort_order.asc(),
                HouseholdMemberRecord.display_name.asc(),
            )
        )
        return [_to_member(record) for record in await self._session.scalars(statement)]

    async def get_member(
        self,
        household_id: UUID,
        member_id: UUID,
    ) -> StoredSettingsMember | None:
        statement = select(HouseholdMemberRecord).where(
            HouseholdMemberRecord.id == member_id,
            HouseholdMemberRecord.household_id == household_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return _to_member(record)

    async def add_member(
        self,
        household_id: UUID,
        member: NewSettingsMemberInput,
    ) -> StoredSettingsMember:
        duplicate_statement = select(HouseholdMemberRecord).where(
            HouseholdMemberRecord.household_id == household_id,
            func.lower(HouseholdMemberRecord.display_name) == member.display_name.strip().lower(),
        )
        duplicate_record = await self._session.scalar(duplicate_statement)
        if duplicate_record is not None:
            if duplicate_record.is_active:
                raise ValueError("Участник с таким именем уже есть.")
            duplicate_record.constraints = member.constraints
            duplicate_record.favorite_cuisines = member.favorite_cuisines
            duplicate_record.profile_note = member.profile_note
            duplicate_record.is_active = True
            await self._session.flush()
            return _to_member(duplicate_record)

        sort_order_statement = select(
            func.coalesce(func.max(HouseholdMemberRecord.sort_order), -1)
        ).where(
            HouseholdMemberRecord.household_id == household_id,
        )
        next_sort_order = int((await self._session.scalar(sort_order_statement)) or -1) + 1
        record = HouseholdMemberRecord(
            household_id=household_id,
            display_name=member.display_name.strip(),
            sort_order=next_sort_order,
            constraints=member.constraints,
            favorite_cuisines=member.favorite_cuisines,
            profile_note=member.profile_note,
            is_active=True,
        )
        self._session.add(record)
        await self._session.flush()
        return _to_member(record)

    async def rename_member(
        self,
        household_id: UUID,
        member_id: UUID,
        display_name: str,
    ) -> StoredSettingsMember:
        normalized_name = display_name.strip()
        record = await self._get_required_member(household_id, member_id)
        duplicate_statement = select(HouseholdMemberRecord).where(
            HouseholdMemberRecord.household_id == household_id,
            func.lower(HouseholdMemberRecord.display_name) == normalized_name.lower(),
            HouseholdMemberRecord.id != member_id,
        )
        duplicate = await self._session.scalar(duplicate_statement)
        if duplicate is not None:
            raise ValueError("Участник с таким именем уже есть.")
        record.display_name = normalized_name
        await self._session.flush()
        return _to_member(record)

    async def set_member_active(
        self,
        household_id: UUID,
        member_id: UUID,
        is_active: bool,
    ) -> StoredSettingsMember:
        record = await self._get_required_member(household_id, member_id)
        record.is_active = is_active
        await self._session.flush()
        return _to_member(record)

    async def update_member_constraints(
        self,
        household_id: UUID,
        member_id: UUID,
        constraints: list[str],
    ) -> StoredSettingsMember:
        record = await self._get_required_member(household_id, member_id)
        record.constraints = constraints
        await self._session.flush()
        return _to_member(record)

    async def update_member_cuisines(
        self,
        household_id: UUID,
        member_id: UUID,
        favorite_cuisines: list[str],
    ) -> StoredSettingsMember:
        record = await self._get_required_member(household_id, member_id)
        record.favorite_cuisines = favorite_cuisines
        await self._session.flush()
        return _to_member(record)

    async def update_member_note(
        self,
        household_id: UUID,
        member_id: UUID,
        profile_note: str | None,
    ) -> StoredSettingsMember:
        record = await self._get_required_member(household_id, member_id)
        record.profile_note = profile_note
        await self._session.flush()
        return _to_member(record)

    async def list_pantry_items(self, household_id: UUID) -> list[StoredSettingsPantryItem]:
        statement = (
            select(PantryItemRecord, IngredientRecord)
            .join(IngredientRecord, PantryItemRecord.ingredient_id == IngredientRecord.id)
            .where(PantryItemRecord.household_id == household_id)
            .order_by(IngredientRecord.canonical_name.asc())
        )
        rows = (await self._session.execute(statement)).all()
        return [_to_pantry_item(record, ingredient) for record, ingredient in rows]

    async def get_pantry_item(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> StoredSettingsPantryItem | None:
        statement = (
            select(PantryItemRecord, IngredientRecord)
            .join(IngredientRecord, PantryItemRecord.ingredient_id == IngredientRecord.id)
            .where(
                PantryItemRecord.id == pantry_item_id,
                PantryItemRecord.household_id == household_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        pantry_item, ingredient = row
        return _to_pantry_item(pantry_item, ingredient)

    async def add_or_update_pantry_item(
        self,
        household_id: UUID,
        pantry_item: PantryItemInput,
    ) -> StoredSettingsPantryItem:
        ingredient = await self._get_or_create_ingredient(
            canonical_name=pantry_item.ingredient_name,
            normalized_name=pantry_item.normalized_name,
        )
        statement = select(PantryItemRecord).where(
            PantryItemRecord.household_id == household_id,
            PantryItemRecord.ingredient_id == ingredient.id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            record = PantryItemRecord(
                household_id=household_id,
                ingredient_id=ingredient.id,
                quantity_value=pantry_item.quantity_value,
                quantity_unit=pantry_item.quantity_unit,
                stock_level=pantry_item.stock_level,
                note=pantry_item.note,
            )
            self._session.add(record)
            await self._session.flush()
            return _to_pantry_item(record, ingredient)

        record.quantity_value = pantry_item.quantity_value
        record.quantity_unit = pantry_item.quantity_unit
        record.stock_level = pantry_item.stock_level
        record.note = pantry_item.note
        await self._session.flush()
        return _to_pantry_item(record, ingredient)

    async def update_pantry_item_stock(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        stock_level: PantryStockLevel,
    ) -> StoredSettingsPantryItem:
        record, ingredient = await self._get_required_pantry_row(household_id, pantry_item_id)
        record.stock_level = stock_level
        await self._session.flush()
        return _to_pantry_item(record, ingredient)

    async def update_pantry_item_note(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        note: str | None,
    ) -> StoredSettingsPantryItem:
        record, ingredient = await self._get_required_pantry_row(household_id, pantry_item_id)
        record.note = note
        await self._session.flush()
        return _to_pantry_item(record, ingredient)

    async def update_pantry_item_quantity(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        *,
        quantity_value: Decimal | None,
        quantity_unit: str | None,
        note: str | None,
    ) -> StoredSettingsPantryItem:
        record, ingredient = await self._get_required_pantry_row(household_id, pantry_item_id)
        record.quantity_value = quantity_value
        record.quantity_unit = quantity_unit
        record.note = note
        await self._session.flush()
        return _to_pantry_item(record, ingredient)

    async def delete_pantry_item(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> None:
        record = await self._get_required_pantry_item(household_id, pantry_item_id)
        await self._session.delete(record)
        await self._session.flush()

    async def list_dish_policies(
        self,
        household_id: UUID,
        verdict: DishFeedbackVerdict | None = None,
    ) -> list[StoredSettingsDishPolicy]:
        statement = (
            select(HouseholdDishPolicyRecord, DishRecord)
            .join(DishRecord, HouseholdDishPolicyRecord.dish_id == DishRecord.id)
            .where(HouseholdDishPolicyRecord.household_id == household_id)
            .order_by(DishRecord.canonical_name.asc())
        )
        if verdict is not None:
            statement = statement.where(HouseholdDishPolicyRecord.verdict == verdict)
        rows = (await self._session.execute(statement)).all()
        return [_to_dish_policy(policy, dish) for policy, dish in rows]

    async def get_dish_policy(
        self,
        household_id: UUID,
        policy_id: UUID,
    ) -> StoredSettingsDishPolicy | None:
        statement = (
            select(HouseholdDishPolicyRecord, DishRecord)
            .join(DishRecord, HouseholdDishPolicyRecord.dish_id == DishRecord.id)
            .where(
                HouseholdDishPolicyRecord.id == policy_id,
                HouseholdDishPolicyRecord.household_id == household_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        policy, dish = row
        return _to_dish_policy(policy, dish)

    async def delete_dish_policy(
        self,
        household_id: UUID,
        policy_id: UUID,
    ) -> None:
        record = await self._get_required_policy(household_id, policy_id)
        await self._session.delete(record)
        await self._session.flush()

    async def _get_required_user(self, user_id: UUID) -> UserRecord:
        record = await self._session.get(UserRecord, user_id)
        if record is None:
            raise ValueError(f"user {user_id} does not exist")
        return record

    async def _get_required_household(self, household_id: UUID) -> HouseholdRecord:
        record = await self._session.get(HouseholdRecord, household_id)
        if record is None:
            raise ValueError(f"household {household_id} does not exist")
        return record

    async def _get_required_member(
        self,
        household_id: UUID,
        member_id: UUID,
    ) -> HouseholdMemberRecord:
        statement = select(HouseholdMemberRecord).where(
            HouseholdMemberRecord.id == member_id,
            HouseholdMemberRecord.household_id == household_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            raise ValueError("Участник не найден.")
        return record

    async def _get_required_pantry_item(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> PantryItemRecord:
        statement = select(PantryItemRecord).where(
            PantryItemRecord.id == pantry_item_id,
            PantryItemRecord.household_id == household_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            raise ValueError("Продукт не найден.")
        return record

    async def _get_required_pantry_row(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> tuple[PantryItemRecord, IngredientRecord]:
        statement = (
            select(PantryItemRecord, IngredientRecord)
            .join(IngredientRecord, PantryItemRecord.ingredient_id == IngredientRecord.id)
            .where(
                PantryItemRecord.id == pantry_item_id,
                PantryItemRecord.household_id == household_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise ValueError("Продукт не найден.")
        return cast(tuple[PantryItemRecord, IngredientRecord], row)

    async def _get_required_policy(
        self,
        household_id: UUID,
        policy_id: UUID,
    ) -> HouseholdDishPolicyRecord:
        statement = select(HouseholdDishPolicyRecord).where(
            HouseholdDishPolicyRecord.id == policy_id,
            HouseholdDishPolicyRecord.household_id == household_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            raise ValueError("Правило по блюду не найдено.")
        return record

    async def _get_or_create_ingredient(
        self,
        *,
        canonical_name: str,
        normalized_name: str,
    ) -> IngredientRecord:
        statement = select(IngredientRecord).where(
            IngredientRecord.normalized_name == normalized_name,
        )
        record = await self._session.scalar(statement)
        if record is not None:
            return record
        record = IngredientRecord(
            canonical_name=canonical_name,
            normalized_name=normalized_name,
        )
        self._session.add(record)
        await self._session.flush()
        return record


def build_settings_repository(session: AsyncSession) -> SqlAlchemySettingsRepository:
    return SqlAlchemySettingsRepository(session)
