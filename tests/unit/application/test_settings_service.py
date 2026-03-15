from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.onboarding.dto import PantryItemInput
from aimealplanner.application.settings import NewSettingsMemberInput, SettingsService
from aimealplanner.application.settings.dto import (
    StoredSettingsDishPolicy,
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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeSession:
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def __call__(self) -> FakeSessionContext:
        return FakeSessionContext(self._session)


@dataclass
class FakeSettingsRepository:
    user: StoredSettingsUser | None = None
    household: StoredSettingsHousehold | None = None
    members: list[StoredSettingsMember] = field(default_factory=list)
    pantry_items: list[StoredSettingsPantryItem] = field(default_factory=list)
    dish_policies: list[StoredSettingsDishPolicy] = field(default_factory=list)
    last_planning_settings: tuple[int, bool, RepeatabilityMode] | None = None

    async def get_user_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> StoredSettingsUser | None:
        if self.user is None or self.user.telegram_user_id != telegram_user_id:
            return None
        return self.user

    async def get_household_by_user_id(self, user_id: UUID) -> StoredSettingsHousehold | None:
        if self.household is None or self.household.user_id != user_id:
            return None
        return self.household

    async def update_household_planning_settings(
        self,
        household_id: UUID,
        *,
        meal_count_per_day: int,
        desserts_enabled: bool,
        repeatability_mode: RepeatabilityMode,
    ) -> None:
        if self.household is None or self.household.id != household_id:
            raise ValueError("household does not exist")
        self.last_planning_settings = (
            meal_count_per_day,
            desserts_enabled,
            repeatability_mode,
        )
        self.household = StoredSettingsHousehold(
            id=self.household.id,
            user_id=self.household.user_id,
            onboarding_completed_at=self.household.onboarding_completed_at,
            default_meal_count_per_day=meal_count_per_day,
            desserts_enabled=desserts_enabled,
            repeatability_mode=repeatability_mode,
        )

    async def update_daily_feedback_reminder(
        self,
        user_id: UUID,
        reminder_time: time | None,
    ) -> None:
        raise NotImplementedError

    async def update_weekly_planning_reminder(
        self,
        user_id: UUID,
        day_of_week: int | None,
        reminder_time: time | None,
    ) -> None:
        raise NotImplementedError

    async def list_members(self, household_id: UUID) -> list[StoredSettingsMember]:
        return [member for member in self.members if member.household_id == household_id]

    async def get_member(
        self,
        household_id: UUID,
        member_id: UUID,
    ) -> StoredSettingsMember | None:
        for member in self.members:
            if member.household_id == household_id and member.id == member_id:
                return member
        return None

    async def add_member(
        self,
        household_id: UUID,
        member: NewSettingsMemberInput,
    ) -> StoredSettingsMember:
        created = StoredSettingsMember(
            id=uuid4(),
            household_id=household_id,
            display_name=member.display_name,
            sort_order=len(self.members),
            constraints=member.constraints,
            favorite_cuisines=member.favorite_cuisines,
            profile_note=member.profile_note,
            is_active=True,
        )
        self.members.append(created)
        return created

    async def rename_member(
        self,
        household_id: UUID,
        member_id: UUID,
        display_name: str,
    ) -> StoredSettingsMember:
        raise NotImplementedError

    async def set_member_active(
        self,
        household_id: UUID,
        member_id: UUID,
        is_active: bool,
    ) -> StoredSettingsMember:
        raise NotImplementedError

    async def update_member_constraints(
        self,
        household_id: UUID,
        member_id: UUID,
        constraints: list[str],
    ) -> StoredSettingsMember:
        raise NotImplementedError

    async def update_member_cuisines(
        self,
        household_id: UUID,
        member_id: UUID,
        favorite_cuisines: list[str],
    ) -> StoredSettingsMember:
        raise NotImplementedError

    async def update_member_note(
        self,
        household_id: UUID,
        member_id: UUID,
        profile_note: str | None,
    ) -> StoredSettingsMember:
        raise NotImplementedError

    async def list_pantry_items(self, household_id: UUID) -> list[StoredSettingsPantryItem]:
        return [item for item in self.pantry_items if True]

    async def get_pantry_item(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
    ) -> StoredSettingsPantryItem | None:
        raise NotImplementedError

    async def add_or_update_pantry_item(
        self,
        household_id: UUID,
        pantry_item: PantryItemInput,
    ) -> StoredSettingsPantryItem:
        raise NotImplementedError

    async def update_pantry_item_stock(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        stock_level: PantryStockLevel,
    ) -> StoredSettingsPantryItem:
        raise NotImplementedError

    async def update_pantry_item_note(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        note: str | None,
    ) -> StoredSettingsPantryItem:
        raise NotImplementedError

    async def update_pantry_item_quantity(
        self,
        household_id: UUID,
        pantry_item_id: UUID,
        *,
        quantity_value: Decimal | None,
        quantity_unit: str | None,
        note: str | None,
    ) -> StoredSettingsPantryItem:
        raise NotImplementedError

    async def delete_pantry_item(self, household_id: UUID, pantry_item_id: UUID) -> None:
        raise NotImplementedError

    async def list_dish_policies(
        self,
        household_id: UUID,
        verdict: DishFeedbackVerdict | None = None,
    ) -> list[StoredSettingsDishPolicy]:
        if verdict is None:
            return list(self.dish_policies)
        return [policy for policy in self.dish_policies if policy.verdict is verdict]

    async def get_dish_policy(
        self,
        household_id: UUID,
        policy_id: UUID,
    ) -> StoredSettingsDishPolicy | None:
        for policy in self.dish_policies:
            if policy.id == policy_id:
                return policy
        return None

    async def delete_dish_policy(self, household_id: UUID, policy_id: UUID) -> None:
        self.dish_policies = [policy for policy in self.dish_policies if policy.id != policy_id]


@dataclass
class FakeSettingsWorld:
    session: FakeSession = field(default_factory=FakeSession)
    repository: FakeSettingsRepository = field(default_factory=FakeSettingsRepository)

    def build_service(self) -> SettingsService:
        session_factory = cast(
            async_sessionmaker[AsyncSession],
            FakeSessionFactory(self.session),
        )
        repositories_factory = cast(
            SettingsRepositoryFactory,
            lambda _session: self.repository,
        )
        return SettingsService(session_factory, repositories_factory)


def _build_world() -> FakeSettingsWorld:
    world = FakeSettingsWorld()
    user = StoredSettingsUser(
        id=uuid4(),
        telegram_user_id=101,
        timezone="Europe/Moscow",
        daily_feedback_reminder_enabled=True,
        daily_feedback_reminder_time=time(20, 0),
        weekly_planning_reminder_enabled=True,
        weekly_planning_reminder_day_of_week=5,
        weekly_planning_reminder_time=time(10, 0),
    )
    household = StoredSettingsHousehold(
        id=uuid4(),
        user_id=user.id,
        onboarding_completed_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        default_meal_count_per_day=3,
        desserts_enabled=False,
        repeatability_mode=RepeatabilityMode.BALANCED,
    )
    world.repository.user = user
    world.repository.household = household
    world.repository.members = [
        StoredSettingsMember(
            id=uuid4(),
            household_id=household.id,
            display_name="Вова",
            sort_order=0,
            constraints=["оливки"],
            favorite_cuisines=["азиатская"],
            profile_note=None,
            is_active=True,
        ),
        StoredSettingsMember(
            id=uuid4(),
            household_id=household.id,
            display_name="Катя",
            sort_order=1,
            constraints=[],
            favorite_cuisines=[],
            profile_note="любит посытнее",
            is_active=False,
        ),
    ]
    world.repository.pantry_items = [
        StoredSettingsPantryItem(
            id=uuid4(),
            ingredient_id=uuid4(),
            ingredient_name="Курица",
            stock_level=PantryStockLevel.HAS,
            quantity_value=Decimal("1.00"),
            quantity_unit="кг",
            note=None,
        ),
    ]
    world.repository.dish_policies = [
        StoredSettingsDishPolicy(
            id=uuid4(),
            dish_id=uuid4(),
            dish_name="Паста",
            verdict=DishFeedbackVerdict.FAVORITE,
            note=None,
        ),
        StoredSettingsDishPolicy(
            id=uuid4(),
            dish_id=uuid4(),
            dish_name="Печень по-строгановски",
            verdict=DishFeedbackVerdict.NEVER_AGAIN,
            note="слишком тяжело",
        ),
    ]
    return world


@pytest.mark.asyncio
async def test_get_home_aggregates_counts() -> None:
    world = _build_world()
    service = world.build_service()

    home_view = await service.get_home(101)

    assert home_view.active_members_count == 1
    assert home_view.inactive_members_count == 1
    assert home_view.pantry_items_count == 1
    assert home_view.favorite_policies_count == 1
    assert home_view.blocked_policies_count == 1


@pytest.mark.asyncio
async def test_update_household_planning_settings_returns_refreshed_household() -> None:
    world = _build_world()
    service = world.build_service()

    updated = await service.update_household_planning_settings(
        101,
        meal_count_per_day=4,
        desserts_enabled=True,
        repeatability_mode=RepeatabilityMode.MORE_VARIETY,
    )

    assert updated.default_meal_count_per_day == 4
    assert updated.desserts_enabled is True
    assert updated.repeatability_mode is RepeatabilityMode.MORE_VARIETY
    assert world.session.commit_count == 1


@pytest.mark.asyncio
async def test_remove_dish_policy_deletes_policy_and_returns_verdict() -> None:
    world = _build_world()
    service = world.build_service()
    policy_id = world.repository.dish_policies[1].id

    verdict = await service.remove_dish_policy(101, policy_id)

    assert verdict is DishFeedbackVerdict.NEVER_AGAIN
    assert [policy.id for policy in world.repository.dish_policies] == [
        world.repository.dish_policies[0].id,
    ]
    assert world.session.commit_count == 1
