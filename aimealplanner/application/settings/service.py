# ruff: noqa: RUF001
from __future__ import annotations

from datetime import time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.onboarding.dto import PantryItemInput
from aimealplanner.application.settings.dto import (
    DishPolicyDetailView,
    DishPolicySettingsView,
    FamilySettingsView,
    MemberSettingsView,
    NewSettingsMemberInput,
    PantrySettingsView,
    SettingsHomeView,
    StoredSettingsHousehold,
    StoredSettingsMember,
    StoredSettingsPantryItem,
    StoredSettingsUser,
)
from aimealplanner.application.settings.repositories import SettingsRepositoryFactory
from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    PantryStockLevel,
    RepeatabilityMode,
)


class SettingsService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: SettingsRepositoryFactory,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory

    async def get_home(self, telegram_user_id: int) -> SettingsHomeView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user, household = await self._get_context(telegram_user_id, repositories)
            members = await repositories.list_members(household.id)
            pantry_items = await repositories.list_pantry_items(household.id)
            policies = await repositories.list_dish_policies(household.id)
            return SettingsHomeView(
                user=user,
                household=household,
                active_members_count=sum(1 for member in members if member.is_active),
                inactive_members_count=sum(1 for member in members if not member.is_active),
                pantry_items_count=len(pantry_items),
                favorite_policies_count=sum(
                    1 for policy in policies if policy.verdict is DishFeedbackVerdict.FAVORITE
                ),
                blocked_policies_count=sum(
                    1 for policy in policies if policy.verdict is DishFeedbackVerdict.NEVER_AGAIN
                ),
            )

    async def update_household_planning_settings(
        self,
        telegram_user_id: int,
        *,
        meal_count_per_day: int,
        desserts_enabled: bool,
        repeatability_mode: RepeatabilityMode,
    ) -> StoredSettingsHousehold:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            await repositories.update_household_planning_settings(
                household.id,
                meal_count_per_day=meal_count_per_day,
                desserts_enabled=desserts_enabled,
                repeatability_mode=repeatability_mode,
            )
            await session.commit()
            refreshed = await repositories.get_household_by_user_id(household.user_id)
            if refreshed is None:
                raise ValueError("Не удалось обновить настройки планирования.")
            return refreshed

    async def update_daily_feedback_reminder(
        self,
        telegram_user_id: int,
        reminder_time: time | None,
    ) -> StoredSettingsUser:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user, _ = await self._get_context(telegram_user_id, repositories)
            await repositories.update_daily_feedback_reminder(user.id, reminder_time)
            await session.commit()
            refreshed = await repositories.get_user_by_telegram_user_id(telegram_user_id)
            if refreshed is None:
                raise ValueError("Не удалось обновить ежедневное напоминание.")
            return refreshed

    async def update_weekly_planning_reminder(
        self,
        telegram_user_id: int,
        *,
        day_of_week: int | None,
        reminder_time: time | None,
    ) -> StoredSettingsUser:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user, _ = await self._get_context(telegram_user_id, repositories)
            await repositories.update_weekly_planning_reminder(
                user.id,
                day_of_week,
                reminder_time,
            )
            await session.commit()
            refreshed = await repositories.get_user_by_telegram_user_id(telegram_user_id)
            if refreshed is None:
                raise ValueError("Не удалось обновить weekly reminder.")
            return refreshed

    async def get_family_view(self, telegram_user_id: int) -> FamilySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            members = await repositories.list_members(household.id)
            return FamilySettingsView(
                household=household,
                active_members=[member for member in members if member.is_active],
                inactive_members=[member for member in members if not member.is_active],
            )

    async def add_member(
        self,
        telegram_user_id: int,
        member: NewSettingsMemberInput,
    ) -> FamilySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            await repositories.add_member(household.id, member)
            await session.commit()
        return await self.get_family_view(telegram_user_id)

    async def rename_member(
        self,
        telegram_user_id: int,
        member_id: UUID,
        display_name: str,
    ) -> FamilySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            await repositories.rename_member(household.id, member_id, display_name)
            await session.commit()
        return await self.get_family_view(telegram_user_id)

    async def set_member_active(
        self,
        telegram_user_id: int,
        member_id: UUID,
        *,
        is_active: bool,
    ) -> FamilySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            await repositories.set_member_active(household.id, member_id, is_active)
            await session.commit()
        return await self.get_family_view(telegram_user_id)

    async def list_member_profiles(self, telegram_user_id: int) -> list[StoredSettingsMember]:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            return [
                member
                for member in await repositories.list_members(household.id)
                if member.is_active
            ]

    async def get_member_view(
        self,
        telegram_user_id: int,
        member_id: UUID,
    ) -> MemberSettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            member = await repositories.get_member(household.id, member_id)
            if member is None:
                raise ValueError("Не удалось открыть выбранного участника.")
            return MemberSettingsView(member=member)

    async def update_member_constraints(
        self,
        telegram_user_id: int,
        member_id: UUID,
        constraints: list[str],
    ) -> MemberSettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            member = await repositories.update_member_constraints(
                household.id, member_id, constraints
            )
            await session.commit()
            return MemberSettingsView(member=member)

    async def update_member_cuisines(
        self,
        telegram_user_id: int,
        member_id: UUID,
        favorite_cuisines: list[str],
    ) -> MemberSettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            member = await repositories.update_member_cuisines(
                household.id,
                member_id,
                favorite_cuisines,
            )
            await session.commit()
            return MemberSettingsView(member=member)

    async def update_member_note(
        self,
        telegram_user_id: int,
        member_id: UUID,
        profile_note: str | None,
    ) -> MemberSettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            member = await repositories.update_member_note(household.id, member_id, profile_note)
            await session.commit()
            return MemberSettingsView(member=member)

    async def get_pantry_view(self, telegram_user_id: int) -> PantrySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            return PantrySettingsView(items=await repositories.list_pantry_items(household.id))

    async def get_pantry_item(
        self,
        telegram_user_id: int,
        pantry_item_id: UUID,
    ) -> StoredSettingsPantryItem:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            item = await repositories.get_pantry_item(household.id, pantry_item_id)
            if item is None:
                raise ValueError("Не удалось открыть выбранный продукт.")
            return item

    async def add_or_update_pantry_item(
        self,
        telegram_user_id: int,
        pantry_item: PantryItemInput,
    ) -> PantrySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            await repositories.add_or_update_pantry_item(household.id, pantry_item)
            await session.commit()
        return await self.get_pantry_view(telegram_user_id)

    async def update_pantry_item_stock(
        self,
        telegram_user_id: int,
        pantry_item_id: UUID,
        stock_level: PantryStockLevel,
    ) -> StoredSettingsPantryItem:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            item = await repositories.update_pantry_item_stock(
                household.id, pantry_item_id, stock_level
            )
            await session.commit()
            return item

    async def update_pantry_item_note(
        self,
        telegram_user_id: int,
        pantry_item_id: UUID,
        note: str | None,
    ) -> StoredSettingsPantryItem:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            item = await repositories.update_pantry_item_note(household.id, pantry_item_id, note)
            await session.commit()
            return item

    async def update_pantry_item_quantity(
        self,
        telegram_user_id: int,
        pantry_item_id: UUID,
        *,
        quantity_value: Decimal | None,
        quantity_unit: str | None,
        note: str | None,
    ) -> StoredSettingsPantryItem:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            item = await repositories.update_pantry_item_quantity(
                household.id,
                pantry_item_id,
                quantity_value=quantity_value,
                quantity_unit=quantity_unit,
                note=note,
            )
            await session.commit()
            return item

    async def delete_pantry_item(
        self,
        telegram_user_id: int,
        pantry_item_id: UUID,
    ) -> PantrySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            await repositories.delete_pantry_item(household.id, pantry_item_id)
            await session.commit()
        return await self.get_pantry_view(telegram_user_id)

    async def get_dish_policy_list(
        self,
        telegram_user_id: int,
        verdict: DishFeedbackVerdict,
    ) -> DishPolicySettingsView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            items = await repositories.list_dish_policies(household.id, verdict)
            return DishPolicySettingsView(verdict=verdict, items=items)

    async def get_dish_policy_detail(
        self,
        telegram_user_id: int,
        policy_id: UUID,
    ) -> DishPolicyDetailView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            policy = await repositories.get_dish_policy(household.id, policy_id)
            if policy is None:
                raise ValueError("Не удалось открыть правило по блюду.")
            return DishPolicyDetailView(policy=policy)

    async def remove_dish_policy(
        self,
        telegram_user_id: int,
        policy_id: UUID,
    ) -> DishFeedbackVerdict:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            _, household = await self._get_context(telegram_user_id, repositories)
            policy = await repositories.get_dish_policy(household.id, policy_id)
            if policy is None:
                raise ValueError("Не удалось найти правило по блюду.")
            await repositories.delete_dish_policy(household.id, policy_id)
            await session.commit()
            return policy.verdict

    async def _get_context(
        self,
        telegram_user_id: int,
        repositories,
    ) -> tuple[StoredSettingsUser, StoredSettingsHousehold]:
        user = await repositories.get_user_by_telegram_user_id(telegram_user_id)
        if user is None:
            raise ValueError("Профиль не найден. Сначала отправь /start.")
        household = await repositories.get_household_by_user_id(user.id)
        if household is None or household.onboarding_completed_at is None:
            raise ValueError("Сначала заверши стартовую настройку через /start.")
        return user, household
