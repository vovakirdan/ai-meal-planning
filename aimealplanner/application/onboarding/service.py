from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.onboarding.dto import (
    DailyReminderInput,
    HouseholdMemberInput,
    HouseholdSettingsInput,
    OnboardingStartResult,
    PantryItemInput,
    WeeklyReminderInput,
)
from aimealplanner.application.onboarding.repositories import (
    OnboardingRepositories,
    OnboardingRepositoryBundleFactory,
)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class OnboardingService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: OnboardingRepositoryBundleFactory,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._clock = clock

    async def start_onboarding(
        self,
        telegram_user_id: int,
        *,
        timezone: str = "Europe/Moscow",
    ) -> OnboardingStartResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                user = await repositories.user_repository.create(telegram_user_id, timezone)

            household = await repositories.household_repository.get_by_user_id(user.id)
            if household is None:
                household = await repositories.household_repository.create_for_user(user.id)

            if household.onboarding_completed_at is None:
                await repositories.household_repository.reset_pending_onboarding(household.id)
                await repositories.user_repository.reset_reminders(user.id)
                await session.commit()
                return OnboardingStartResult(
                    user_id=user.id,
                    household_id=household.id,
                    already_completed=False,
                )

            return OnboardingStartResult(
                user_id=user.id,
                household_id=household.id,
                already_completed=True,
            )

    async def save_household_settings(
        self,
        telegram_user_id: int,
        settings: HouseholdSettingsInput,
    ) -> None:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household_id = await self._get_context(telegram_user_id, repositories)
            await repositories.household_repository.update_household_settings(
                household_id,
                settings,
            )
            await session.commit()

    async def save_member_profile(
        self,
        telegram_user_id: int,
        member: HouseholdMemberInput,
    ) -> None:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household_id = await self._get_context(telegram_user_id, repositories)
            await repositories.household_repository.upsert_member(household_id, member)
            await session.commit()

    async def save_daily_feedback_reminder(
        self,
        telegram_user_id: int,
        reminder: DailyReminderInput,
    ) -> None:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user_id, _ = await self._get_context(telegram_user_id, repositories)
            await repositories.user_repository.update_daily_feedback_reminder(
                user_id,
                reminder.reminder_time,
            )
            await session.commit()

    async def save_weekly_planning_reminder(
        self,
        telegram_user_id: int,
        reminder: WeeklyReminderInput,
    ) -> None:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user_id, _ = await self._get_context(telegram_user_id, repositories)
            await repositories.user_repository.update_weekly_planning_reminder(
                user_id,
                reminder.day_of_week,
                reminder.reminder_time,
            )
            await session.commit()

    async def add_pantry_item(
        self,
        telegram_user_id: int,
        pantry_item: PantryItemInput,
    ) -> None:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household_id = await self._get_context(telegram_user_id, repositories)
            ingredient = await repositories.ingredient_repository.get_by_normalized_name(
                pantry_item.normalized_name,
            )
            if ingredient is None:
                ingredient = await repositories.ingredient_repository.create(
                    pantry_item.ingredient_name,
                    pantry_item.normalized_name,
                )
            await repositories.household_repository.add_or_update_pantry_item(
                household_id,
                ingredient.id,
                pantry_item,
            )
            await session.commit()

    async def complete_onboarding(self, telegram_user_id: int) -> None:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household_id = await self._get_context(telegram_user_id, repositories)
            await repositories.household_repository.complete_onboarding(
                household_id,
                self._clock(),
            )
            await session.commit()

    async def _get_context(
        self,
        telegram_user_id: int,
        repositories: OnboardingRepositories,
    ) -> tuple[UUID, UUID]:
        user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
        if user is None:
            raise ValueError("onboarding context is missing user; restart with /start")

        household = await repositories.household_repository.get_by_user_id(user.id)
        if household is None:
            raise ValueError("onboarding context is missing household; restart with /start")

        return user.id, household.id
