from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.planning import PlanDraftInput, PlanningService
from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDayView,
    StoredPlanItemView,
    StoredPlanMealView,
    StoredPlanOverview,
)
from aimealplanner.application.planning.dto import (
    PlanDraftResult,
    StoredDraftPlan,
    StoredPlanningHousehold,
    StoredPlanningUser,
)
from aimealplanner.application.planning.generation_dto import (
    GeneratedWeekPlan,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import PlannedMealItemReplacement
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
    WeeklyPlanRepository,
)
from aimealplanner.infrastructure.db.enums import RepeatabilityMode
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
    created_drafts: list[tuple[UUID, str, list[str], PlanDraftInput]] = field(default_factory=list)
    existing_drafts_by_household_id: dict[UUID, list[StoredDraftPlan]] = field(default_factory=dict)
    deleted_household_ids: list[UUID] = field(default_factory=list)

    async def get_latest_draft_for_household(self, household_id: UUID) -> StoredDraftPlan | None:
        drafts = self.existing_drafts_by_household_id.get(household_id, [])
        if not drafts:
            return None
        return drafts[-1]

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        self.deleted_household_ids.append(household_id)
        deleted_count = len(self.existing_drafts_by_household_id.get(household_id, []))
        self.existing_drafts_by_household_id[household_id] = []
        return deleted_count

    async def get_plan_overview(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> StoredPlanOverview | None:
        raise NotImplementedError

    async def get_day_view(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> StoredPlanDayView | None:
        raise NotImplementedError

    async def get_meal_view(
        self,
        household_id: UUID,
        planned_meal_id: UUID,
    ) -> StoredPlanMealView | None:
        raise NotImplementedError

    async def get_item_view(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> StoredPlanItemView | None:
        raise NotImplementedError

    async def update_item_snapshot(self, replacement: PlannedMealItemReplacement) -> None:
        _ = replacement
        raise NotImplementedError

    async def create_draft(
        self,
        household_id: UUID,
        timezone: str,
        active_slots: list[str],
        draft: PlanDraftInput,
    ) -> PlanDraftResult:
        self.created_drafts.append((household_id, timezone, active_slots, draft))
        return PlanDraftResult(
            weekly_plan_id=uuid4(),
            start_date=draft.start_date,
            end_date=draft.end_date,
            active_slots=active_slots,
            pantry_considered=draft.pantry_considered,
        )

    async def get_generation_context(
        self,
        weekly_plan_id: UUID,
    ) -> WeeklyPlanGenerationContext | None:
        raise NotImplementedError

    async def replace_generated_meals(
        self,
        weekly_plan_id: UUID,
        generated_plan: GeneratedWeekPlan,
    ) -> None:
        raise NotImplementedError


@dataclass
class FakePlanningWorld:
    session: FakeSession = field(default_factory=FakeSession)
    user_repository: FakePlanningUserRepository = field(default_factory=FakePlanningUserRepository)
    household_repository: FakePlanningHouseholdRepository = field(
        default_factory=FakePlanningHouseholdRepository,
    )
    weekly_plan_repository: FakeWeeklyPlanRepository = field(
        default_factory=FakeWeeklyPlanRepository,
    )

    def build_service(self, *, now: datetime) -> PlanningService:
        repositories = PlanningRepositories(
            user_repository=self.user_repository,
            household_repository=self.household_repository,
            weekly_plan_repository=cast(
                WeeklyPlanRepository,
                self.weekly_plan_repository,
            ),
        )
        session_factory = cast(
            async_sessionmaker[AsyncSession],
            FakeSessionFactory(self.session),
        )
        repositories_factory = cast(
            PlanningRepositoryBundleFactory,
            lambda _session: repositories,
        )
        return PlanningService(
            session_factory,
            repositories_factory,
            clock=lambda: now,
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
async def test_start_planning_returns_default_next_full_week_for_midweek_date() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    context = await service.start_planning(user.telegram_user_id)

    assert context.today_local_date == date(2026, 3, 18)
    assert context.default_start_date == date(2026, 3, 23)
    assert context.default_end_date == date(2026, 3, 29)
    assert context.default_meal_count_per_day == 3
    assert context.pantry_items_count == 2
    assert context.existing_draft is None


@pytest.mark.asyncio
async def test_start_planning_requires_completed_onboarding() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    incomplete_household = StoredPlanningHousehold(
        id=household.id,
        user_id=household.user_id,
        onboarding_completed_at=None,
        default_meal_count_per_day=household.default_meal_count_per_day,
        desserts_enabled=household.desserts_enabled,
        repeatability_mode=household.repeatability_mode,
        pantry_items_count=household.pantry_items_count,
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = incomplete_household
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    with pytest.raises(ValueError, match="Сначала заверши стартовую настройку"):
        await service.start_planning(user.telegram_user_id)


@pytest.mark.asyncio
async def test_create_plan_draft_persists_template_and_context() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    result = await service.create_plan_draft(
        user.telegram_user_id,
        PlanDraftInput(
            start_date=date(2026, 3, 23),
            end_date=date(2026, 3, 29),
            meal_count_per_day=4,
            desserts_enabled=True,
            week_mood="Азиатская",
            weekly_notes="побольше простых блюд",
            pantry_considered=True,
            context_payload={"source": "test"},
        ),
    )

    assert world.session.commit_count == 1
    assert result.active_slots == ["breakfast", "lunch", "dinner", "snack_1", "dessert"]
    assert world.weekly_plan_repository.created_drafts == [
        (
            household.id,
            "Europe/Moscow",
            ["breakfast", "lunch", "dinner", "snack_1", "dessert"],
            PlanDraftInput(
                start_date=date(2026, 3, 23),
                end_date=date(2026, 3, 29),
                meal_count_per_day=4,
                desserts_enabled=True,
                week_mood="Азиатская",
                weekly_notes="побольше простых блюд",
                pantry_considered=True,
                context_payload={"source": "test"},
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_start_planning_returns_existing_draft_context() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    existing_draft = StoredDraftPlan(
        id=uuid4(),
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 29),
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.existing_drafts_by_household_id[household.id] = [existing_draft]
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    context = await service.start_planning(user.telegram_user_id)

    assert context.existing_draft == existing_draft


@pytest.mark.asyncio
async def test_discard_existing_drafts_deletes_household_drafts_and_commits() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    existing_draft = StoredDraftPlan(
        id=uuid4(),
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 29),
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.existing_drafts_by_household_id[household.id] = [existing_draft]
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    deleted_count = await service.discard_existing_drafts(user.telegram_user_id)

    assert deleted_count == 1
    assert world.session.commit_count == 1
    assert world.weekly_plan_repository.deleted_household_ids == [household.id]
    assert world.weekly_plan_repository.existing_drafts_by_household_id[household.id] == []


@pytest.mark.asyncio
async def test_create_plan_draft_rejects_pantry_usage_when_pantry_is_empty() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = StoredPlanningHousehold(
        id=household.id,
        user_id=household.user_id,
        onboarding_completed_at=household.onboarding_completed_at,
        default_meal_count_per_day=household.default_meal_count_per_day,
        desserts_enabled=household.desserts_enabled,
        repeatability_mode=household.repeatability_mode,
        pantry_items_count=0,
    )
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    with pytest.raises(ValueError, match="Нечего учитывать в запасах"):
        await service.create_plan_draft(
            user.telegram_user_id,
            PlanDraftInput(
                start_date=date(2026, 3, 23),
                end_date=date(2026, 3, 29),
                meal_count_per_day=3,
                desserts_enabled=False,
                week_mood=None,
                weekly_notes=None,
                pantry_considered=True,
                context_payload={"source": "test"},
            ),
        )


@pytest.mark.asyncio
async def test_create_plan_draft_rejects_past_start_date() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    service = world.build_service(now=datetime(2026, 3, 18, 9, 0, tzinfo=UTC))

    with pytest.raises(ValueError, match="Нельзя начать план с даты, которая уже прошла"):
        await service.create_plan_draft(
            user.telegram_user_id,
            PlanDraftInput(
                start_date=date(2026, 3, 17),
                end_date=date(2026, 3, 23),
                meal_count_per_day=3,
                desserts_enabled=False,
                week_mood=None,
                weekly_notes=None,
                pantry_considered=False,
                context_payload={"source": "test"},
            ),
        )
