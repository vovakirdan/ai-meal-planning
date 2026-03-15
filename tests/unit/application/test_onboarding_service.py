from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.onboarding import (
    DailyReminderInput,
    HouseholdMemberInput,
    HouseholdSettingsInput,
    OnboardingService,
    PantryItemInput,
    WeeklyReminderInput,
)
from aimealplanner.application.onboarding.dto import (
    StoredHousehold,
    StoredIngredient,
    StoredUser,
)
from aimealplanner.application.onboarding.repositories import (
    OnboardingRepositories,
    OnboardingRepositoryBundleFactory,
)
from aimealplanner.infrastructure.db.enums import PantryStockLevel, RepeatabilityMode
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
class FakeUserRepository:
    users_by_tg_id: dict[int, StoredUser] = field(default_factory=dict)
    users_by_id: dict[UUID, StoredUser] = field(default_factory=dict)
    reset_user_ids: list[UUID] = field(default_factory=list)
    daily_reminders: dict[UUID, time | None] = field(default_factory=dict)
    weekly_reminders: dict[UUID, tuple[int | None, time | None]] = field(default_factory=dict)

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredUser | None:
        return self.users_by_tg_id.get(telegram_user_id)

    async def create(self, telegram_user_id: int, timezone: str) -> StoredUser:
        user = StoredUser(
            id=uuid4(),
            telegram_user_id=telegram_user_id,
            timezone=timezone,
        )
        self.users_by_tg_id[telegram_user_id] = user
        self.users_by_id[user.id] = user
        return user

    async def reset_reminders(self, user_id: UUID) -> None:
        self.reset_user_ids.append(user_id)
        self.daily_reminders[user_id] = None
        self.weekly_reminders[user_id] = (None, None)

    async def update_daily_feedback_reminder(
        self,
        user_id: UUID,
        reminder_time: time | None,
    ) -> None:
        self.daily_reminders[user_id] = reminder_time

    async def update_weekly_planning_reminder(
        self,
        user_id: UUID,
        day_of_week: int | None,
        reminder_time: time | None,
    ) -> None:
        self.weekly_reminders[user_id] = (day_of_week, reminder_time)


@dataclass
class FakeHouseholdRepository:
    households_by_user_id: dict[UUID, StoredHousehold] = field(default_factory=dict)
    households_by_id: dict[UUID, StoredHousehold] = field(default_factory=dict)
    reset_household_ids: list[UUID] = field(default_factory=list)
    member_payloads: dict[UUID, list[HouseholdMemberInput]] = field(default_factory=dict)
    pantry_payloads: dict[UUID, list[tuple[UUID, PantryItemInput]]] = field(default_factory=dict)
    settings_by_household_id: dict[UUID, HouseholdSettingsInput] = field(default_factory=dict)

    async def get_by_user_id(self, user_id: UUID) -> StoredHousehold | None:
        return self.households_by_user_id.get(user_id)

    async def create_for_user(self, user_id: UUID) -> StoredHousehold:
        household = StoredHousehold(
            id=uuid4(),
            user_id=user_id,
            onboarding_completed_at=None,
        )
        self.households_by_user_id[user_id] = household
        self.households_by_id[household.id] = household
        return household

    async def reset_pending_onboarding(self, household_id: UUID) -> None:
        self.reset_household_ids.append(household_id)
        household = self.households_by_id[household_id]
        self.households_by_id[household_id] = StoredHousehold(
            id=household.id,
            user_id=household.user_id,
            onboarding_completed_at=None,
        )
        self.households_by_user_id[household.user_id] = self.households_by_id[household_id]
        self.member_payloads[household_id] = []
        self.pantry_payloads[household_id] = []

    async def update_household_settings(
        self,
        household_id: UUID,
        settings: HouseholdSettingsInput,
    ) -> None:
        self.settings_by_household_id[household_id] = settings

    async def upsert_member(
        self,
        household_id: UUID,
        member: HouseholdMemberInput,
    ) -> None:
        self.member_payloads.setdefault(household_id, [])
        members = [
            existing
            for existing in self.member_payloads[household_id]
            if existing.sort_order != member.sort_order
        ]
        members.append(member)
        self.member_payloads[household_id] = sorted(members, key=lambda item: item.sort_order)

    async def add_or_update_pantry_item(
        self,
        household_id: UUID,
        ingredient_id: UUID,
        pantry_item: PantryItemInput,
    ) -> None:
        self.pantry_payloads.setdefault(household_id, [])
        items = [
            existing
            for existing in self.pantry_payloads[household_id]
            if existing[0] != ingredient_id
        ]
        items.append((ingredient_id, pantry_item))
        self.pantry_payloads[household_id] = items

    async def complete_onboarding(self, household_id: UUID, completed_at: datetime) -> None:
        household = self.households_by_id[household_id]
        completed_household = StoredHousehold(
            id=household.id,
            user_id=household.user_id,
            onboarding_completed_at=completed_at,
        )
        self.households_by_id[household_id] = completed_household
        self.households_by_user_id[household.user_id] = completed_household


@dataclass
class FakeIngredientRepository:
    ingredients_by_name: dict[str, StoredIngredient] = field(default_factory=dict)

    async def get_by_normalized_name(self, normalized_name: str) -> StoredIngredient | None:
        return self.ingredients_by_name.get(normalized_name)

    async def create(self, canonical_name: str, normalized_name: str) -> StoredIngredient:
        ingredient = StoredIngredient(
            id=uuid4(),
            canonical_name=canonical_name,
            normalized_name=normalized_name,
        )
        self.ingredients_by_name[normalized_name] = ingredient
        return ingredient


@dataclass
class FakeOnboardingWorld:
    session: FakeSession = field(default_factory=FakeSession)
    user_repository: FakeUserRepository = field(default_factory=FakeUserRepository)
    household_repository: FakeHouseholdRepository = field(
        default_factory=FakeHouseholdRepository,
    )
    ingredient_repository: FakeIngredientRepository = field(
        default_factory=FakeIngredientRepository
    )

    def build_service(self) -> OnboardingService:
        repositories = OnboardingRepositories(
            user_repository=self.user_repository,
            household_repository=self.household_repository,
            ingredient_repository=self.ingredient_repository,
        )
        session_factory = cast(
            async_sessionmaker[AsyncSession],
            FakeSessionFactory(self.session),
        )
        repositories_factory = cast(
            OnboardingRepositoryBundleFactory,
            lambda _session: repositories,
        )
        return OnboardingService(session_factory, repositories_factory)


@pytest.mark.asyncio
async def test_start_onboarding_creates_user_household_and_resets_pending_state() -> None:
    world = FakeOnboardingWorld()
    service = world.build_service()

    result = await service.start_onboarding(telegram_user_id=101)

    assert result.already_completed is False
    assert world.session.commit_count == 1
    assert result.user_id in world.user_repository.users_by_id
    assert result.household_id in world.household_repository.households_by_id
    assert world.user_repository.reset_user_ids == [result.user_id]
    assert world.household_repository.reset_household_ids == [result.household_id]


@pytest.mark.asyncio
async def test_start_onboarding_returns_completed_context_without_reset() -> None:
    world = FakeOnboardingWorld()
    user = await world.user_repository.create(telegram_user_id=101, timezone="Europe/Moscow")
    completed_household = StoredHousehold(
        id=uuid4(),
        user_id=user.id,
        onboarding_completed_at=datetime(2026, 3, 15, 9, 0, tzinfo=UTC),
    )
    world.household_repository.households_by_id[completed_household.id] = completed_household
    world.household_repository.households_by_user_id[user.id] = completed_household
    service = world.build_service()

    result = await service.start_onboarding(telegram_user_id=101)

    assert result.already_completed is True
    assert world.session.commit_count == 0
    assert world.user_repository.reset_user_ids == []
    assert world.household_repository.reset_household_ids == []


@pytest.mark.asyncio
async def test_service_persists_household_member_and_reminders() -> None:
    world = FakeOnboardingWorld()
    service = world.build_service()
    start_result = await service.start_onboarding(telegram_user_id=101)

    await service.save_household_settings(
        telegram_user_id=101,
        settings=HouseholdSettingsInput(
            meal_count_per_day=4,
            desserts_enabled=True,
            repeatability_mode=RepeatabilityMode.MORE_VARIETY,
        ),
    )
    await service.save_member_profile(
        telegram_user_id=101,
        member=HouseholdMemberInput(
            sort_order=0,
            display_name="Вова",
            constraints=["оливки"],
            favorite_cuisines=["азиатская"],
            profile_note="не любит слишком острое",
        ),
    )
    await service.save_daily_feedback_reminder(
        telegram_user_id=101,
        reminder=DailyReminderInput(reminder_time=time(hour=20, minute=30)),
    )
    await service.save_weekly_planning_reminder(
        telegram_user_id=101,
        reminder=WeeklyReminderInput(day_of_week=5, reminder_time=time(hour=11, minute=0)),
    )

    assert world.session.commit_count == 5
    assert world.household_repository.settings_by_household_id[start_result.household_id] == (
        HouseholdSettingsInput(
            meal_count_per_day=4,
            desserts_enabled=True,
            repeatability_mode=RepeatabilityMode.MORE_VARIETY,
        )
    )
    assert world.household_repository.member_payloads[start_result.household_id] == [
        HouseholdMemberInput(
            sort_order=0,
            display_name="Вова",
            constraints=["оливки"],
            favorite_cuisines=["азиатская"],
            profile_note="не любит слишком острое",
        ),
    ]
    assert world.user_repository.daily_reminders[start_result.user_id] == time(
        hour=20,
        minute=30,
    )
    assert world.user_repository.weekly_reminders[start_result.user_id] == (
        5,
        time(hour=11, minute=0),
    )


@pytest.mark.asyncio
async def test_add_pantry_item_creates_ingredient_and_completes_onboarding() -> None:
    world = FakeOnboardingWorld()
    service = world.build_service()
    start_result = await service.start_onboarding(telegram_user_id=101)

    await service.add_pantry_item(
        telegram_user_id=101,
        pantry_item=PantryItemInput(
            ingredient_name="Пармезан",
            normalized_name="пармезан",
            stock_level=PantryStockLevel.HAS,
            quantity_value=Decimal("0.5"),
            quantity_unit="кг",
            note=None,
        ),
    )
    await service.complete_onboarding(telegram_user_id=101)

    ingredient = world.ingredient_repository.ingredients_by_name["пармезан"]
    pantry_items = world.household_repository.pantry_payloads[start_result.household_id]

    assert world.session.commit_count == 3
    assert pantry_items == [
        (
            ingredient.id,
            PantryItemInput(
                ingredient_name="Пармезан",
                normalized_name="пармезан",
                stock_level=PantryStockLevel.HAS,
                quantity_value=Decimal("0.5"),
                quantity_unit="кг",
                note=None,
            ),
        ),
    ]
    assert (
        world.household_repository.households_by_id[
            start_result.household_id
        ].onboarding_completed_at
        is not None
    )
