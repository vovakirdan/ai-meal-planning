# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.planning import DishReviewService, ReviewQueueEntry
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
    PlanningMemberContext,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
    WeeklyPlanRepository,
)
from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    RepeatabilityMode,
    WeeklyPlanStatus,
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
class FakePlanningUserRepository:
    users_by_tg_id: dict[int, StoredPlanningUser] = field(default_factory=dict)

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredPlanningUser | None:
        return self.users_by_tg_id.get(telegram_user_id)


@dataclass
class FakePlanningHouseholdRepository:
    households_by_user_id: dict[UUID, StoredPlanningHousehold] = field(default_factory=dict)
    members_by_household_id: dict[UUID, list[StoredPlanningMember]] = field(default_factory=dict)

    async def get_by_user_id(self, user_id: UUID) -> StoredPlanningHousehold | None:
        return self.households_by_user_id.get(user_id)

    async def list_members(self, household_id: UUID) -> list[StoredPlanningMember]:
        return self.members_by_household_id.get(household_id, [])


@dataclass
class UpsertedFeedbackEvent:
    household_id: UUID
    household_member_id: UUID
    planned_meal_item_id: UUID
    dish_id: UUID
    feedback_date: date
    verdict: DishFeedbackVerdict
    raw_comment: str | None
    normalized_notes: dict[str, object]


@dataclass
class FakeWeeklyPlanRepository:
    latest_confirmed_by_household_id: dict[UUID, StoredPlanReference] = field(default_factory=dict)
    overviews_by_plan_id: dict[UUID, StoredPlanOverview] = field(default_factory=dict)
    day_views_by_key: dict[tuple[UUID, date], StoredPlanDayView] = field(default_factory=dict)
    meal_views_by_id: dict[UUID, StoredPlanMealView] = field(default_factory=dict)
    item_views_by_id: dict[UUID, StoredPlanItemView] = field(default_factory=dict)
    generation_contexts_by_plan_id: dict[UUID, WeeklyPlanGenerationContext] = field(
        default_factory=dict,
    )
    dish_ids_by_item_id: dict[UUID, UUID] = field(default_factory=dict)
    upserted_feedback_events: list[UpsertedFeedbackEvent] = field(default_factory=list)

    async def get_latest_draft_for_household(self, household_id: UUID) -> StoredDraftPlan | None:
        _ = household_id
        raise NotImplementedError

    async def get_latest_confirmed_for_household(
        self,
        household_id: UUID,
    ) -> StoredPlanReference | None:
        return self.latest_confirmed_by_household_id.get(household_id)

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        _ = household_id
        raise NotImplementedError

    async def get_plan_overview(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> StoredPlanOverview | None:
        _ = household_id
        return self.overviews_by_plan_id.get(weekly_plan_id)

    async def get_day_view(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> StoredPlanDayView | None:
        _ = household_id
        return self.day_views_by_key.get((weekly_plan_id, meal_date))

    async def get_meal_view(
        self,
        household_id: UUID,
        planned_meal_id: UUID,
    ) -> StoredPlanMealView | None:
        _ = household_id
        return self.meal_views_by_id.get(planned_meal_id)

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
        _ = (household_id, dish_id, verdict, note)
        raise NotImplementedError

    async def delete_item(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID:
        _ = (household_id, planned_meal_item_id)
        raise NotImplementedError

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
        draft: PlanDraftInput,
    ) -> PlanDraftResult:
        _ = (household_id, timezone, active_slots, draft)
        raise NotImplementedError

    async def confirm_plan(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        confirmed_at: datetime,
    ) -> PlanConfirmationResult:
        _ = (household_id, weekly_plan_id, confirmed_at)
        raise NotImplementedError

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
        self.upserted_feedback_events.append(
            UpsertedFeedbackEvent(
                household_id=household_id,
                household_member_id=household_member_id,
                planned_meal_item_id=planned_meal_item_id,
                dish_id=dish_id,
                feedback_date=feedback_date,
                verdict=verdict,
                raw_comment=raw_comment,
                normalized_notes=normalized_notes,
            ),
        )


@dataclass
class FakeCommentClient:
    response: dict[str, object]
    observed_member_name: str | None = None
    observed_verdict: DishFeedbackVerdict | None = None
    observed_comment: str | None = None

    async def normalize_feedback_comment(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        household_member_name: str,
        verdict: DishFeedbackVerdict,
        raw_comment: str,
    ) -> dict[str, object]:
        _ = (item_view, generation_context)
        self.observed_member_name = household_member_name
        self.observed_verdict = verdict
        self.observed_comment = raw_comment
        return self.response


@dataclass
class FakeReviewWorld:
    session: FakeSession = field(default_factory=FakeSession)
    user_repository: FakePlanningUserRepository = field(default_factory=FakePlanningUserRepository)
    household_repository: FakePlanningHouseholdRepository = field(
        default_factory=FakePlanningHouseholdRepository,
    )
    weekly_plan_repository: FakeWeeklyPlanRepository = field(
        default_factory=FakeWeeklyPlanRepository,
    )
    comment_client: FakeCommentClient = field(
        default_factory=lambda: FakeCommentClient(response={}),
    )

    def build_service(self) -> DishReviewService:
        repositories = PlanningRepositories(
            user_repository=self.user_repository,
            household_repository=self.household_repository,
            weekly_plan_repository=cast(WeeklyPlanRepository, self.weekly_plan_repository),
        )
        return DishReviewService(
            cast(async_sessionmaker[AsyncSession], FakeSessionFactory(self.session)),
            cast(
                PlanningRepositoryBundleFactory,
                lambda _session: repositories,
            ),
            comment_client=self.comment_client,
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


def _build_member(household_id: UUID, display_name: str, sort_order: int) -> StoredPlanningMember:
    return StoredPlanningMember(
        id=uuid4(),
        household_id=household_id,
        display_name=display_name,
        sort_order=sort_order,
        is_active=True,
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
            DishQuickAction(label="Легче", instruction="Сделай блюдо легче."),
            DishQuickAction(label="Мягче вкус", instruction="Сделай вкус мягче."),
        ],
        household_policy_verdict=None,
        household_policy_note=None,
    )


def _build_generation_context(weekly_plan_id: UUID) -> WeeklyPlanGenerationContext:
    return WeeklyPlanGenerationContext(
        weekly_plan_id=weekly_plan_id,
        household_id=uuid4(),
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
                constraints=["без оливок"],
                favorite_cuisines=["русская"],
                profile_note=None,
            ),
        ],
        pantry_items=[],
    )


@pytest.mark.asyncio
async def test_start_review_returns_only_days_with_real_dishes() -> None:
    world = FakeReviewWorld()
    service = world.build_service()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.latest_confirmed_by_household_id[household.id] = (
        StoredPlanReference(
            id=weekly_plan_id,
            start_date=date(2026, 3, 23),
            end_date=date(2026, 3, 29),
            status=WeeklyPlanStatus.CONFIRMED,
        )
    )
    world.weekly_plan_repository.overviews_by_plan_id[weekly_plan_id] = StoredPlanOverview(
        weekly_plan_id=weekly_plan_id,
        status=WeeklyPlanStatus.CONFIRMED,
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 29),
        days=[
            StoredPlanDaySummary(
                meal_date=date(2026, 3, 23),
                meals_count=1,
                meals=[
                    StoredPlanMealSummary(
                        planned_meal_id=uuid4(),
                        slot="dinner",
                        note=None,
                        item_names=["Паста с курицей"],
                    ),
                ],
            ),
            StoredPlanDaySummary(
                meal_date=date(2026, 3, 24),
                meals_count=1,
                meals=[
                    StoredPlanMealSummary(
                        planned_meal_id=uuid4(),
                        slot="dinner",
                        note=None,
                        item_names=[],
                    ),
                ],
            ),
        ],
    )

    context = await service.start_review(user.telegram_user_id)

    assert context.weekly_plan_id == weekly_plan_id
    assert [day.meal_date for day in context.days] == [date(2026, 3, 23)]
    assert context.days[0].items_count == 1


@pytest.mark.asyncio
async def test_start_day_review_expands_queue_by_items_and_members() -> None:
    world = FakeReviewWorld()
    service = world.build_service()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    meal_id = uuid4()
    first_item_id = uuid4()
    second_item_id = uuid4()
    first_member = _build_member(household.id, "Вова", 0)
    second_member = _build_member(household.id, "Катя", 1)

    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.household_repository.members_by_household_id[household.id] = [
        first_member,
        second_member,
    ]
    world.weekly_plan_repository.latest_confirmed_by_household_id[household.id] = (
        StoredPlanReference(
            id=weekly_plan_id,
            start_date=date(2026, 3, 23),
            end_date=date(2026, 3, 29),
            status=WeeklyPlanStatus.CONFIRMED,
        )
    )
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, date(2026, 3, 23))] = (
        StoredPlanDayView(
            weekly_plan_id=weekly_plan_id,
            meal_date=date(2026, 3, 23),
            meals=[
                StoredPlanMealSummary(
                    planned_meal_id=meal_id,
                    slot="dinner",
                    note=None,
                    item_names=["Паста с курицей", "Салат"],
                ),
            ],
        )
    )
    world.weekly_plan_repository.meal_views_by_id[meal_id] = StoredPlanMealView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=meal_id,
        meal_date=date(2026, 3, 23),
        slot="dinner",
        note=None,
        items=[
            StoredMealItemSummary(
                planned_meal_item_id=first_item_id,
                position=0,
                name="Паста с курицей",
            ),
            StoredMealItemSummary(
                planned_meal_item_id=second_item_id,
                position=1,
                name="Салат",
            ),
        ],
    )

    session = await service.start_day_review(
        user.telegram_user_id,
        weekly_plan_id=weekly_plan_id,
        meal_date=date(2026, 3, 23),
    )

    assert len(session.entries) == 4
    assert session.entries[0] == ReviewQueueEntry(
        planned_meal_item_id=first_item_id,
        meal_date=date(2026, 3, 23),
        slot="dinner",
        dish_name="Паста с курицей",
        household_member_id=first_member.id,
        household_member_name="Вова",
    )
    assert session.entries[1].household_member_name == "Катя"
    assert session.entries[2].dish_name == "Салат"


@pytest.mark.asyncio
async def test_save_feedback_materializes_dish_and_persists_normalized_notes() -> None:
    world = FakeReviewWorld(
        comment_client=FakeCommentClient(
            response={
                "planning_note": "Сделать блюдо менее жирным.",
                "restriction_candidate": "избегать слишком жирных сливочных блюд",
            },
        ),
    )
    service = world.build_service()
    user, household = _build_user_and_household()
    planned_meal_item_id = uuid4()
    entry = ReviewQueueEntry(
        planned_meal_item_id=planned_meal_item_id,
        meal_date=date(2026, 3, 23),
        slot="dinner",
        dish_name="Паста с курицей",
        household_member_id=uuid4(),
        household_member_name="Вова",
    )
    item_view = _build_item_view(planned_meal_item_id)

    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = item_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[item_view.weekly_plan_id] = (
        _build_generation_context(item_view.weekly_plan_id)
    )

    result = await service.save_feedback(
        user.telegram_user_id,
        entry=entry,
        verdict=DishFeedbackVerdict.RARELY_REPEAT,
        raw_comment="Слишком жирно, хочется мягче.",
    )

    assert result.normalized_notes == {
        "planning_note": "Сделать блюдо менее жирным.",
        "restriction_candidate": "избегать слишком жирных сливочных блюд",
    }
    assert world.comment_client.observed_member_name == "Вова"
    assert world.comment_client.observed_verdict == DishFeedbackVerdict.RARELY_REPEAT
    assert world.session.commit_count == 1
    assert len(world.weekly_plan_repository.upserted_feedback_events) == 1
    saved_event = world.weekly_plan_repository.upserted_feedback_events[0]
    assert saved_event.planned_meal_item_id == planned_meal_item_id
    assert saved_event.verdict == DishFeedbackVerdict.RARELY_REPEAT
    assert saved_event.normalized_notes == result.normalized_notes
    assert (
        saved_event.dish_id
        == world.weekly_plan_repository.item_views_by_id[planned_meal_item_id].dish_id
    )
