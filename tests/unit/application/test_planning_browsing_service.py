from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDaySummary,
    StoredPlanOverview,
)
from aimealplanner.application.planning.browsing_service import PlanningBrowsingService
from aimealplanner.application.planning.dto import (
    PlanDraftInput,
    PlanDraftResult,
    StoredDraftPlan,
    StoredPlanningHousehold,
    StoredPlanningUser,
)
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)
from aimealplanner.infrastructure.db.enums import RepeatabilityMode
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class FakeSession:
    async def commit(self) -> None:
        return None


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
class FakePlanningUserRepository:
    users_by_tg_id: dict[int, StoredPlanningUser] = field(default_factory=dict)

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredPlanningUser | None:
        return self.users_by_tg_id.get(telegram_user_id)


@dataclass
class FakePlanningHouseholdRepository:
    households_by_user_id: dict[UUID, StoredPlanningHousehold] = field(default_factory=dict)

    async def get_by_user_id(self, user_id: UUID) -> StoredPlanningHousehold | None:
        return self.households_by_user_id.get(user_id)


@dataclass
class FakeWeeklyPlanRepository:
    latest_draft_by_household_id: dict[UUID, UUID] = field(default_factory=dict)
    overviews_by_plan_id: dict[UUID, StoredPlanOverview] = field(default_factory=dict)

    async def get_latest_draft_for_household(self, household_id: UUID) -> StoredDraftPlan | None:
        weekly_plan_id = self.latest_draft_by_household_id.get(household_id)
        if weekly_plan_id is None:
            return None
        overview = self.overviews_by_plan_id[weekly_plan_id]
        return StoredDraftPlan(
            id=overview.weekly_plan_id,
            start_date=overview.start_date,
            end_date=overview.end_date,
        )

    async def get_plan_overview(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> StoredPlanOverview | None:
        _ = household_id
        return self.overviews_by_plan_id.get(weekly_plan_id)

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        _ = household_id
        raise NotImplementedError

    async def get_day_view(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
    ):
        _ = (household_id, weekly_plan_id, meal_date)
        raise NotImplementedError

    async def get_meal_view(self, household_id: UUID, planned_meal_id: UUID):
        _ = (household_id, planned_meal_id)
        raise NotImplementedError

    async def get_item_view(self, household_id: UUID, planned_meal_item_id: UUID):
        _ = (household_id, planned_meal_item_id)
        raise NotImplementedError

    async def get_generation_context(self, weekly_plan_id: UUID):
        _ = weekly_plan_id
        raise NotImplementedError

    async def replace_generated_meals(self, weekly_plan_id: UUID, generated_plan: object) -> None:
        _ = (weekly_plan_id, generated_plan)
        raise NotImplementedError

    async def create_draft(
        self,
        household_id: UUID,
        timezone: str,
        active_slots: list[str],
        draft: PlanDraftInput,
    ) -> PlanDraftResult:
        _ = (household_id, timezone, active_slots, draft)
        raise NotImplementedError


def _build_service(
    user_repository: FakePlanningUserRepository,
    household_repository: FakePlanningHouseholdRepository,
    weekly_plan_repository: FakeWeeklyPlanRepository,
) -> PlanningBrowsingService:
    repositories = PlanningRepositories(
        user_repository=user_repository,
        household_repository=household_repository,
        weekly_plan_repository=weekly_plan_repository,
    )
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        FakeSessionFactory(FakeSession()),
    )
    repositories_factory = cast(
        PlanningRepositoryBundleFactory,
        lambda _session: repositories,
    )
    return PlanningBrowsingService(
        session_factory,
        repositories_factory,
    )


def _build_user_and_household() -> tuple[StoredPlanningUser, StoredPlanningHousehold]:
    user_id = uuid4()
    return (
        StoredPlanningUser(
            id=user_id,
            telegram_user_id=101,
            timezone="Europe/Moscow",
        ),
        StoredPlanningHousehold(
            id=uuid4(),
            user_id=user_id,
            onboarding_completed_at=datetime(2026, 3, 15, 8, 0, tzinfo=UTC),
            default_meal_count_per_day=3,
            desserts_enabled=False,
            repeatability_mode=RepeatabilityMode.BALANCED,
            pantry_items_count=2,
        ),
    )


@pytest.mark.asyncio
async def test_get_latest_draft_overview_renders_days_message() -> None:
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    weekly_plan_repository.latest_draft_by_household_id[household.id] = weekly_plan_id
    weekly_plan_repository.overviews_by_plan_id[weekly_plan_id] = StoredPlanOverview(
        weekly_plan_id=weekly_plan_id,
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 29),
        days=[
            StoredPlanDaySummary(meal_date=date(2026, 3, 23), meals_count=4),
            StoredPlanDaySummary(meal_date=date(2026, 3, 24), meals_count=4),
        ],
    )
    service = _build_service(user_repository, household_repository, weekly_plan_repository)

    overview = await service.get_latest_draft_overview(user.telegram_user_id)

    assert overview.weekly_plan_id == weekly_plan_id
    assert "Текущий план недели." in overview.text
    assert "Выбери день" in overview.text


@pytest.mark.asyncio
async def test_get_latest_draft_overview_requires_existing_draft() -> None:
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    service = _build_service(user_repository, household_repository, weekly_plan_repository)

    with pytest.raises(ValueError, match="Текущего черновика пока нет"):
        await service.get_latest_draft_overview(user.telegram_user_id)
