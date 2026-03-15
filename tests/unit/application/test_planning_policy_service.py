# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.dto import (
    StoredPlanningHousehold,
    StoredPlanningUser,
)
from aimealplanner.application.planning.generation_dto import (
    DishQuickAction,
    PlanningMemberContext,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.policy_service import DishPolicyService
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
    WeeklyPlanRepository,
)
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict, RepeatabilityMode
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
    item_views_by_id: dict[UUID, StoredPlanItemView] = field(default_factory=dict)
    dish_ids_by_item_id: dict[UUID, UUID] = field(default_factory=dict)
    policy_notes_by_dish_id: dict[UUID, str | None] = field(default_factory=dict)
    generation_contexts_by_plan_id: dict[UUID, WeeklyPlanGenerationContext] = field(
        default_factory=dict,
    )
    deleted_item_ids: list[UUID] = field(default_factory=list)

    async def get_latest_draft_for_household(self, household_id: UUID) -> None:
        _ = household_id
        raise NotImplementedError

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        _ = household_id
        raise NotImplementedError

    async def get_plan_overview(self, household_id: UUID, weekly_plan_id: UUID) -> None:
        _ = (household_id, weekly_plan_id)
        raise NotImplementedError

    async def get_day_view(self, household_id: UUID, weekly_plan_id: UUID, meal_date: date) -> None:
        _ = (household_id, weekly_plan_id, meal_date)
        raise NotImplementedError

    async def get_meal_view(self, household_id: UUID, planned_meal_id: UUID) -> None:
        _ = (household_id, planned_meal_id)
        raise NotImplementedError

    async def get_item_view(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> StoredPlanItemView | None:
        _ = household_id
        return self.item_views_by_id.get(planned_meal_item_id)

    async def update_item_snapshot(self, replacement: object) -> None:
        _ = replacement
        raise NotImplementedError

    async def ensure_item_dish(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID:
        _ = household_id
        dish_id = self.dish_ids_by_item_id.setdefault(planned_meal_item_id, uuid4())
        item = self.item_views_by_id[planned_meal_item_id]
        self.item_views_by_id[planned_meal_item_id] = StoredPlanItemView(
            weekly_plan_id=item.weekly_plan_id,
            planned_meal_id=item.planned_meal_id,
            planned_meal_item_id=item.planned_meal_item_id,
            dish_id=dish_id,
            meal_date=item.meal_date,
            slot=item.slot,
            name=item.name,
            summary=item.summary,
            adaptation_notes=item.adaptation_notes,
            snapshot_payload=item.snapshot_payload,
            suggested_actions=item.suggested_actions,
            household_policy_verdict=item.household_policy_verdict,
            household_policy_note=item.household_policy_note,
        )
        return dish_id

    async def upsert_household_dish_policy(
        self,
        household_id: UUID,
        dish_id: UUID,
        verdict: DishFeedbackVerdict,
        note: str | None,
    ) -> None:
        _ = household_id
        self.policy_notes_by_dish_id[dish_id] = note
        for item_id, current_dish_id in self.dish_ids_by_item_id.items():
            if current_dish_id != dish_id:
                continue
            item = self.item_views_by_id[item_id]
            self.item_views_by_id[item_id] = StoredPlanItemView(
                weekly_plan_id=item.weekly_plan_id,
                planned_meal_id=item.planned_meal_id,
                planned_meal_item_id=item.planned_meal_item_id,
                dish_id=item.dish_id,
                meal_date=item.meal_date,
                slot=item.slot,
                name=item.name,
                summary=item.summary,
                adaptation_notes=item.adaptation_notes,
                snapshot_payload=item.snapshot_payload,
                suggested_actions=item.suggested_actions,
                household_policy_verdict=verdict,
                household_policy_note=note,
            )

    async def delete_item(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID:
        _ = household_id
        self.deleted_item_ids.append(planned_meal_item_id)
        item = self.item_views_by_id.pop(planned_meal_item_id)
        self.dish_ids_by_item_id.pop(planned_meal_item_id, None)
        return item.planned_meal_id

    async def get_generation_context(
        self,
        weekly_plan_id: UUID,
    ) -> WeeklyPlanGenerationContext | None:
        return self.generation_contexts_by_plan_id.get(weekly_plan_id)

    async def replace_generated_meals(self, weekly_plan_id: UUID, generated_plan: object) -> None:
        _ = (weekly_plan_id, generated_plan)
        raise NotImplementedError

    async def create_draft(
        self,
        household_id: UUID,
        timezone: str,
        active_slots: list[str],
        draft: object,
    ) -> object:
        _ = (household_id, timezone, active_slots, draft)
        raise NotImplementedError


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


def _build_item_view(planned_meal_item_id: UUID) -> StoredPlanItemView:
    return StoredPlanItemView(
        weekly_plan_id=uuid4(),
        planned_meal_id=uuid4(),
        planned_meal_item_id=planned_meal_item_id,
        dish_id=None,
        meal_date=date(2026, 3, 23),
        slot="dinner",
        name="Паста с курицей",
        summary="Сливочная паста на ужин",
        adaptation_notes=[],
        snapshot_payload={"summary": "Сливочная паста на ужин"},
        suggested_actions=[
            DishQuickAction(
                label="Легче",
                instruction="Сделай блюдо легче.",
            ),
            DishQuickAction(
                label="Мягче вкус",
                instruction="Сделай вкус блюда мягче.",
            ),
        ],
        household_policy_verdict=None,
        household_policy_note=None,
    )


def _build_generation_context(
    weekly_plan_id: UUID,
    household_id: UUID,
) -> WeeklyPlanGenerationContext:
    return WeeklyPlanGenerationContext(
        weekly_plan_id=weekly_plan_id,
        household_id=household_id,
        timezone="Europe/Moscow",
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 29),
        meal_count_per_day=3,
        desserts_enabled=False,
        repeatability_mode=RepeatabilityMode.BALANCED,
        active_slots=["breakfast", "lunch", "dinner"],
        week_mood=None,
        weekly_notes=None,
        pantry_considered=False,
        context_payload={"source": "test"},
        members=[
            PlanningMemberContext(
                display_name="Вова",
                constraints=[],
                favorite_cuisines=[],
                profile_note=None,
            ),
        ],
        pantry_items=[],
    )


@dataclass
class FakeReasonClient:
    normalized_note: str | None
    observed_raw_reason: str | None = None

    async def normalize_policy_reason(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        verdict_label: str,
        raw_reason: str,
    ) -> str | None:
        _ = (item_view, generation_context, verdict_label)
        self.observed_raw_reason = raw_reason
        return self.normalized_note


def _build_service(
    session: FakeSession,
    user_repository: FakePlanningUserRepository,
    household_repository: FakePlanningHouseholdRepository,
    weekly_plan_repository: FakeWeeklyPlanRepository,
    *,
    reason_client: FakeReasonClient | None = None,
) -> DishPolicyService:
    repositories = PlanningRepositories(
        user_repository=user_repository,
        household_repository=household_repository,
        weekly_plan_repository=cast(WeeklyPlanRepository, weekly_plan_repository),
    )
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        FakeSessionFactory(session),
    )
    repositories_factory = cast(
        PlanningRepositoryBundleFactory,
        lambda _session: repositories,
    )
    return DishPolicyService(
        session_factory,
        repositories_factory,
        reason_client=reason_client,
    )


@pytest.mark.asyncio
async def test_set_household_policy_materializes_dish_and_persists_verdict() -> None:
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    planned_meal_item_id = uuid4()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    weekly_plan_repository.item_views_by_id[planned_meal_item_id] = _build_item_view(
        planned_meal_item_id,
    )
    service = _build_service(
        session,
        user_repository,
        household_repository,
        weekly_plan_repository,
    )

    result = await service.set_household_policy(
        user.telegram_user_id,
        planned_meal_item_id,
        verdict=DishFeedbackVerdict.NEVER_AGAIN,
    )

    assert session.commit_count == 1
    assert result.updated_item.dish_id is not None
    assert result.updated_item.household_policy_verdict is DishFeedbackVerdict.NEVER_AGAIN


@pytest.mark.asyncio
async def test_set_household_policy_normalizes_reason_when_client_is_available() -> None:
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    reason_client = FakeReasonClient(normalized_note="избегать оливок в семейных блюдах")
    user, household = _build_user_and_household()
    planned_meal_item_id = uuid4()
    item_view = _build_item_view(planned_meal_item_id)
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    weekly_plan_repository.item_views_by_id[planned_meal_item_id] = item_view
    weekly_plan_repository.generation_contexts_by_plan_id[item_view.weekly_plan_id] = (
        _build_generation_context(item_view.weekly_plan_id, household.id)
    )
    service = _build_service(
        session,
        user_repository,
        household_repository,
        weekly_plan_repository,
        reason_client=reason_client,
    )

    result = await service.set_household_policy(
        user.telegram_user_id,
        planned_meal_item_id,
        verdict=DishFeedbackVerdict.NEVER_AGAIN,
        raw_reason="Не любим оливки",
    )

    assert reason_client.observed_raw_reason == "Не любим оливки"
    assert result.updated_item.household_policy_note == "избегать оливок в семейных блюдах"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_remove_item_from_current_plan_deletes_snapshot_item() -> None:
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    planned_meal_item_id = uuid4()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    weekly_plan_repository.item_views_by_id[planned_meal_item_id] = _build_item_view(
        planned_meal_item_id,
    )
    service = _build_service(
        session,
        user_repository,
        household_repository,
        weekly_plan_repository,
    )

    result = await service.remove_item_from_current_plan(
        user.telegram_user_id,
        planned_meal_item_id,
    )

    assert result.updated_meal_id is not None
    assert weekly_plan_repository.deleted_item_ids == [planned_meal_item_id]
    assert planned_meal_item_id not in weekly_plan_repository.item_views_by_id
    assert session.commit_count == 1
