from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.onboarding.dto import (
    HouseholdMemberInput,
    HouseholdSettingsInput,
    PantryItemInput,
    StoredHousehold,
    StoredIngredient,
    StoredUser,
)
from aimealplanner.application.onboarding.repositories import OnboardingRepositories
from aimealplanner.infrastructure.db.enums import RepeatabilityMode
from aimealplanner.infrastructure.db.models.household import (
    HouseholdMemberRecord,
    HouseholdRecord,
    PantryItemRecord,
)
from aimealplanner.infrastructure.db.models.ingredient import IngredientRecord
from aimealplanner.infrastructure.db.models.user import UserRecord


def _to_user(record: UserRecord) -> StoredUser:
    return StoredUser(
        id=record.id,
        telegram_user_id=record.telegram_user_id,
        timezone=record.timezone,
    )


def _to_household(record: HouseholdRecord) -> StoredHousehold:
    return StoredHousehold(
        id=record.id,
        user_id=record.user_id,
        onboarding_completed_at=record.onboarding_completed_at,
    )


def _to_ingredient(record: IngredientRecord) -> StoredIngredient:
    return StoredIngredient(
        id=record.id,
        canonical_name=record.canonical_name,
        normalized_name=record.normalized_name,
    )


class SqlAlchemyUserOnboardingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredUser | None:
        statement = select(UserRecord).where(UserRecord.telegram_user_id == telegram_user_id)
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return _to_user(record)

    async def create(self, telegram_user_id: int, timezone: str) -> StoredUser:
        record = UserRecord(
            telegram_user_id=telegram_user_id,
            timezone=timezone,
        )
        self._session.add(record)
        await self._session.flush()
        return _to_user(record)

    async def reset_reminders(self, user_id: UUID) -> None:
        record = await self._get_required_user(user_id)
        record.daily_feedback_reminder_enabled = False
        record.daily_feedback_reminder_time = None
        record.weekly_planning_reminder_enabled = False
        record.weekly_planning_reminder_day_of_week = None
        record.weekly_planning_reminder_time = None

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

    async def _get_required_user(self, user_id: UUID) -> UserRecord:
        record = await self._session.get(UserRecord, user_id)
        if record is None:
            raise ValueError(f"user {user_id} does not exist")
        return record


class SqlAlchemyHouseholdOnboardingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> StoredHousehold | None:
        statement = select(HouseholdRecord).where(HouseholdRecord.user_id == user_id)
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return _to_household(record)

    async def create_for_user(self, user_id: UUID) -> StoredHousehold:
        record = HouseholdRecord(user_id=user_id)
        self._session.add(record)
        await self._session.flush()
        return _to_household(record)

    async def reset_pending_onboarding(self, household_id: UUID) -> None:
        household = await self._get_required_household(household_id)
        await self._session.execute(
            delete(PantryItemRecord).where(PantryItemRecord.household_id == household_id),
        )
        await self._session.execute(
            delete(HouseholdMemberRecord).where(HouseholdMemberRecord.household_id == household_id),
        )
        household.default_meal_count_per_day = 3
        household.desserts_enabled = False
        household.repeatability_mode = RepeatabilityMode.BALANCED
        household.onboarding_completed_at = None

    async def update_household_settings(
        self,
        household_id: UUID,
        settings: HouseholdSettingsInput,
    ) -> None:
        household = await self._get_required_household(household_id)
        household.default_meal_count_per_day = settings.meal_count_per_day
        household.desserts_enabled = settings.desserts_enabled
        household.repeatability_mode = settings.repeatability_mode

    async def upsert_member(
        self,
        household_id: UUID,
        member: HouseholdMemberInput,
    ) -> None:
        statement = select(HouseholdMemberRecord).where(
            HouseholdMemberRecord.household_id == household_id,
            HouseholdMemberRecord.sort_order == member.sort_order,
        )
        record = await self._session.scalar(statement)
        if record is None:
            record = HouseholdMemberRecord(
                household_id=household_id,
                sort_order=member.sort_order,
                display_name=member.display_name,
                constraints=member.constraints,
                favorite_cuisines=member.favorite_cuisines,
                profile_note=member.profile_note,
                is_active=True,
            )
            self._session.add(record)
            await self._session.flush()
            return

        record.display_name = member.display_name
        record.constraints = member.constraints
        record.favorite_cuisines = member.favorite_cuisines
        record.profile_note = member.profile_note
        record.is_active = True

    async def add_or_update_pantry_item(
        self,
        household_id: UUID,
        ingredient_id: UUID,
        pantry_item: PantryItemInput,
    ) -> None:
        statement = select(PantryItemRecord).where(
            PantryItemRecord.household_id == household_id,
            PantryItemRecord.ingredient_id == ingredient_id,
        )
        record = await self._session.scalar(statement)
        if record is None:
            record = PantryItemRecord(
                household_id=household_id,
                ingredient_id=ingredient_id,
                quantity_value=pantry_item.quantity_value,
                quantity_unit=pantry_item.quantity_unit,
                stock_level=pantry_item.stock_level,
                note=pantry_item.note,
            )
            self._session.add(record)
            await self._session.flush()
            return

        record.quantity_value = pantry_item.quantity_value
        record.quantity_unit = pantry_item.quantity_unit
        record.stock_level = pantry_item.stock_level
        record.note = pantry_item.note

    async def complete_onboarding(self, household_id: UUID, completed_at: datetime) -> None:
        household = await self._get_required_household(household_id)
        household.onboarding_completed_at = completed_at

    async def _get_required_household(self, household_id: UUID) -> HouseholdRecord:
        record = await self._session.get(HouseholdRecord, household_id)
        if record is None:
            raise ValueError(f"household {household_id} does not exist")
        return record


class SqlAlchemyIngredientCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_normalized_name(self, normalized_name: str) -> StoredIngredient | None:
        statement = select(IngredientRecord).where(
            IngredientRecord.normalized_name == normalized_name,
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return _to_ingredient(record)

    async def create(self, canonical_name: str, normalized_name: str) -> StoredIngredient:
        record = IngredientRecord(
            canonical_name=canonical_name,
            normalized_name=normalized_name,
        )
        self._session.add(record)
        await self._session.flush()
        return _to_ingredient(record)


def build_onboarding_repositories(session: AsyncSession) -> OnboardingRepositories:
    return OnboardingRepositories(
        user_repository=SqlAlchemyUserOnboardingRepository(session),
        household_repository=SqlAlchemyHouseholdOnboardingRepository(session),
        ingredient_repository=SqlAlchemyIngredientCatalogRepository(session),
    )
