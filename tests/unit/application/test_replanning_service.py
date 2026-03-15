# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.planning import PlanReplanningService
from aimealplanner.application.planning.browsing_dto import (
    StoredMealItemSummary,
    StoredPlanDayView,
    StoredPlanMealSummary,
    StoredPlanMealView,
)
from aimealplanner.application.planning.dto import (
    StoredPlanningHousehold,
    StoredPlanningMember,
    StoredPlanningUser,
)
from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedMealItem,
    GeneratedWeekPlan,
    PlanningMemberContext,
    RecipeHint,
    WeeklyPlanGenerationContext,
)
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

    async def list_members(self, household_id: UUID) -> list[StoredPlanningMember]:
        _ = household_id
        raise NotImplementedError


@dataclass
class FakeWeeklyPlanRepository:
    meal_views_by_id: dict[UUID, StoredPlanMealView] = field(default_factory=dict)
    day_views_by_key: dict[tuple[UUID, date], StoredPlanDayView] = field(default_factory=dict)
    generation_contexts_by_plan_id: dict[UUID, WeeklyPlanGenerationContext] = field(
        default_factory=dict,
    )
    replaced_meals: list[tuple[UUID, UUID, GeneratedMeal]] = field(default_factory=list)
    replaced_days: list[tuple[UUID, UUID, date, GeneratedWeekPlan]] = field(default_factory=list)

    async def get_latest_draft_for_household(self, household_id: UUID) -> None:
        _ = household_id
        raise NotImplementedError

    async def get_latest_confirmed_for_household(self, household_id: UUID) -> None:
        _ = household_id
        raise NotImplementedError

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        _ = household_id
        raise NotImplementedError

    async def get_plan_overview(self, household_id: UUID, weekly_plan_id: UUID) -> None:
        _ = (household_id, weekly_plan_id)
        raise NotImplementedError

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

    async def get_item_view(self, household_id: UUID, planned_meal_item_id: UUID) -> None:
        _ = (household_id, planned_meal_item_id)
        raise NotImplementedError

    async def update_item_snapshot(self, replacement: object) -> None:
        _ = replacement
        raise NotImplementedError

    async def replace_meal_with_generated(
        self,
        household_id: UUID,
        planned_meal_id: UUID,
        generated_meal: GeneratedMeal,
    ) -> None:
        existing_meal = self.meal_views_by_id[planned_meal_id]
        self.replaced_meals.append((household_id, planned_meal_id, generated_meal))
        self.meal_views_by_id[planned_meal_id] = StoredPlanMealView(
            weekly_plan_id=existing_meal.weekly_plan_id,
            planned_meal_id=planned_meal_id,
            meal_date=generated_meal.meal_date,
            slot=generated_meal.slot,
            note=generated_meal.note,
            items=[
                StoredMealItemSummary(
                    planned_meal_item_id=uuid4(),
                    position=index,
                    name=item.name,
                )
                for index, item in enumerate(generated_meal.items)
            ],
        )

    async def replace_day_with_generated(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        meal_date: date,
        generated_plan: GeneratedWeekPlan,
    ) -> None:
        self.replaced_days.append((household_id, weekly_plan_id, meal_date, generated_plan))
        self.day_views_by_key[(weekly_plan_id, meal_date)] = StoredPlanDayView(
            weekly_plan_id=weekly_plan_id,
            meal_date=meal_date,
            meals=[
                StoredPlanMealSummary(
                    planned_meal_id=uuid4(),
                    slot=meal.slot,
                    note=meal.note,
                    item_names=[item.name for item in meal.items],
                )
                for meal in generated_plan.meals
            ],
        )

    async def ensure_item_dish(self, household_id: UUID, planned_meal_item_id: UUID) -> UUID:
        _ = (household_id, planned_meal_item_id)
        raise NotImplementedError

    async def upsert_household_dish_policy(
        self,
        household_id: UUID,
        dish_id: UUID,
        verdict: object,
        note: str | None,
    ) -> None:
        _ = (household_id, dish_id, verdict, note)
        raise NotImplementedError

    async def delete_item(self, household_id: UUID, planned_meal_item_id: UUID) -> UUID:
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
        draft: object,
    ) -> object:
        _ = (household_id, timezone, active_slots, draft)
        raise NotImplementedError

    async def confirm_plan(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
        confirmed_at: datetime,
    ) -> object:
        _ = (household_id, weekly_plan_id, confirmed_at)
        raise NotImplementedError

    async def upsert_feedback_event(
        self,
        household_id: UUID,
        household_member_id: UUID,
        planned_meal_item_id: UUID,
        dish_id: UUID,
        feedback_date: date,
        verdict: object,
        raw_comment: str | None,
        normalized_notes: dict[str, object],
    ) -> None:
        _ = (
            household_id,
            household_member_id,
            planned_meal_item_id,
            dish_id,
            feedback_date,
            verdict,
            raw_comment,
            normalized_notes,
        )
        raise NotImplementedError

    async def get_shopping_source(self, household_id: UUID, weekly_plan_id: UUID) -> None:
        _ = (household_id, weekly_plan_id)
        raise NotImplementedError

    async def create_shopping_list(self, weekly_plan_id: UUID, items: list[object]) -> object:
        _ = (weekly_plan_id, items)
        raise NotImplementedError


@dataclass
class FakeGenerationClient:
    result: GeneratedWeekPlan
    observed_contexts: list[WeeklyPlanGenerationContext] = field(default_factory=list)

    async def generate_week_plan(
        self,
        context: WeeklyPlanGenerationContext,
    ) -> GeneratedWeekPlan:
        self.observed_contexts.append(context)
        return self.result


@dataclass
class FakeRecipeHintProvider:
    result: list[RecipeHint]
    observed_contexts: list[WeeklyPlanGenerationContext] = field(default_factory=list)
    observed_queries: list[str] = field(default_factory=list)

    async def collect_hints(
        self,
        context: WeeklyPlanGenerationContext,
    ) -> list[RecipeHint]:
        self.observed_contexts.append(context)
        return self.result

    async def search_related_recipes(
        self,
        query: str,
        context: WeeklyPlanGenerationContext,
    ) -> list[RecipeHint]:
        _ = context
        self.observed_queries.append(query)
        return self.result


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

    def build_service(
        self,
        *,
        generation_client: FakeGenerationClient,
        recipe_hint_provider: FakeRecipeHintProvider | None = None,
    ) -> PlanReplanningService:
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
        return PlanReplanningService(
            session_factory,
            repositories_factory,
            generation_client=generation_client,
            recipe_hint_provider=recipe_hint_provider,
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
            pantry_items_count=1,
        ),
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
        week_mood="Средиземноморская",
        weekly_notes="побольше быстрых ужинов",
        pantry_considered=True,
        context_payload={"source": "test"},
        members=[
            PlanningMemberContext(
                display_name="Вова",
                constraints=["без оливок"],
                favorite_cuisines=["итальянская"],
                profile_note="любит простые ужины",
            ),
        ],
        pantry_items=[],
    )


def _build_recipe_hint() -> RecipeHint:
    return RecipeHint(
        provider="spoonacular",
        external_id="recipe-1",
        title="Skillet Chicken Pasta",
        source_url=None,
        cuisines=["Italian"],
        diets=[],
        summary="Quick pasta for weeknights",
        ready_in_minutes=25,
        servings=2,
        ingredients=[],
    )


def _build_meal_view(weekly_plan_id: UUID, planned_meal_id: UUID) -> StoredPlanMealView:
    return StoredPlanMealView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=planned_meal_id,
        meal_date=date(2026, 3, 24),
        slot="dinner",
        note="Сделать поинтереснее",
        items=[
            StoredMealItemSummary(
                planned_meal_item_id=uuid4(),
                position=0,
                name="Паста с курицей",
            ),
        ],
    )


def _build_day_view(weekly_plan_id: UUID) -> StoredPlanDayView:
    return StoredPlanDayView(
        weekly_plan_id=weekly_plan_id,
        meal_date=date(2026, 3, 24),
        meals=[
            StoredPlanMealSummary(
                planned_meal_id=uuid4(),
                slot="breakfast",
                note=None,
                item_names=["Овсянка с ягодами"],
            ),
            StoredPlanMealSummary(
                planned_meal_id=uuid4(),
                slot="lunch",
                note=None,
                item_names=["Куриный суп"],
            ),
            StoredPlanMealSummary(
                planned_meal_id=uuid4(),
                slot="dinner",
                note="Сделать поинтереснее",
                item_names=["Паста с курицей"],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_replan_meal_scopes_context_and_updates_selected_meal() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_id = uuid4()
    meal_view = _build_meal_view(weekly_plan_id, planned_meal_id)
    day_view = _build_day_view(weekly_plan_id)
    generation_context = _build_generation_context(weekly_plan_id, household.id)
    generation_client = FakeGenerationClient(
        result=GeneratedWeekPlan(
            meals=[
                GeneratedMeal(
                    meal_date=meal_view.meal_date,
                    slot=meal_view.slot,
                    note="Новый ужин",
                    items=[
                        GeneratedMealItem(
                            name="Рис с индейкой",
                            summary="Более легкий ужин",
                            adaptation_notes=["без оливок"],
                            suggested_actions=[],
                        ),
                    ],
                ),
            ],
        ),
    )
    hint_provider = FakeRecipeHintProvider(result=[_build_recipe_hint()])
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.meal_views_by_id[planned_meal_id] = meal_view
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, meal_view.meal_date)] = day_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = generation_context
    service = world.build_service(
        generation_client=generation_client,
        recipe_hint_provider=hint_provider,
    )

    result = await service.replan_meal(user.telegram_user_id, planned_meal_id)

    observed_context = generation_client.observed_contexts[0]
    assert observed_context.start_date == meal_view.meal_date
    assert observed_context.end_date == meal_view.meal_date
    assert observed_context.active_slots == [meal_view.slot]
    assert observed_context.context_payload["replanning_scope"] == "meal"
    assert observed_context.context_payload["replanning_target_slot"] == "dinner"
    assert "Паста с курицей" in cast(
        str, observed_context.context_payload["replanning_current_scope"]
    )
    assert hint_provider.observed_contexts[0].active_slots == [meal_view.slot]
    assert world.weekly_plan_repository.replaced_meals[0][1] == planned_meal_id
    assert [item.name for item in result.updated_meal.items] == ["Рис с индейкой"]
    assert world.session.commit_count == 1


@pytest.mark.asyncio
async def test_replan_day_scopes_context_and_updates_day() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    day_view = _build_day_view(weekly_plan_id)
    generation_context = _build_generation_context(weekly_plan_id, household.id)
    generation_client = FakeGenerationClient(
        result=GeneratedWeekPlan(
            meals=[
                GeneratedMeal(
                    meal_date=day_view.meal_date,
                    slot="breakfast",
                    note=None,
                    items=[
                        GeneratedMealItem(
                            name="Сырники",
                            summary="Быстрый завтрак",
                            adaptation_notes=[],
                            suggested_actions=[],
                        ),
                    ],
                ),
                GeneratedMeal(
                    meal_date=day_view.meal_date,
                    slot="lunch",
                    note=None,
                    items=[
                        GeneratedMealItem(
                            name="Лапша с овощами",
                            summary="Простой обед",
                            adaptation_notes=[],
                            suggested_actions=[],
                        ),
                    ],
                ),
                GeneratedMeal(
                    meal_date=day_view.meal_date,
                    slot="dinner",
                    note="Новый ужин",
                    items=[
                        GeneratedMealItem(
                            name="Запеченная рыба",
                            summary="Спокойный ужин",
                            adaptation_notes=["без лука"],
                            suggested_actions=[],
                        ),
                    ],
                ),
            ],
        ),
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, day_view.meal_date)] = day_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = generation_context
    service = world.build_service(generation_client=generation_client)

    result = await service.replan_day(
        user.telegram_user_id,
        weekly_plan_id,
        day_view.meal_date,
    )

    observed_context = generation_client.observed_contexts[0]
    assert observed_context.start_date == day_view.meal_date
    assert observed_context.end_date == day_view.meal_date
    assert observed_context.active_slots == ["breakfast", "lunch", "dinner"]
    assert observed_context.context_payload["replanning_scope"] == "day"
    assert observed_context.context_payload["replanning_target_date"] == (
        day_view.meal_date.isoformat()
    )
    assert "Паста с курицей" in cast(
        str,
        observed_context.context_payload["replanning_current_day"],
    )
    assert world.weekly_plan_repository.replaced_days[0][1] == weekly_plan_id
    assert [meal.item_names[0] for meal in result.updated_day.meals] == [
        "Сырники",
        "Лапша с овощами",
        "Запеченная рыба",
    ]
    assert world.session.commit_count == 1


@pytest.mark.asyncio
async def test_replan_day_rejects_incomplete_generated_slots() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    day_view = _build_day_view(weekly_plan_id)
    generation_context = _build_generation_context(weekly_plan_id, household.id)
    generation_client = FakeGenerationClient(
        result=GeneratedWeekPlan(
            meals=[
                GeneratedMeal(
                    meal_date=day_view.meal_date,
                    slot="breakfast",
                    note=None,
                    items=[
                        GeneratedMealItem(
                            name="Сырники",
                            summary="Быстрый завтрак",
                            adaptation_notes=[],
                            suggested_actions=[],
                        ),
                    ],
                ),
                GeneratedMeal(
                    meal_date=day_view.meal_date,
                    slot="dinner",
                    note=None,
                    items=[
                        GeneratedMealItem(
                            name="Рыба с рисом",
                            summary="Спокойный ужин",
                            adaptation_notes=[],
                            suggested_actions=[],
                        ),
                    ],
                ),
            ],
        ),
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, day_view.meal_date)] = day_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = generation_context
    service = world.build_service(generation_client=generation_client)

    with pytest.raises(ValueError, match="неполный или несовместимый"):
        await service.replan_day(user.telegram_user_id, weekly_plan_id, day_view.meal_date)


@pytest.mark.asyncio
async def test_replan_meal_rejects_wrong_slot_from_ai() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_id = uuid4()
    meal_view = _build_meal_view(weekly_plan_id, planned_meal_id)
    day_view = _build_day_view(weekly_plan_id)
    generation_context = _build_generation_context(weekly_plan_id, household.id)
    generation_client = FakeGenerationClient(
        result=GeneratedWeekPlan(
            meals=[
                GeneratedMeal(
                    meal_date=meal_view.meal_date,
                    slot="lunch",
                    note=None,
                    items=[
                        GeneratedMealItem(
                            name="Курица с рисом",
                            summary="Обычный обед",
                            adaptation_notes=[],
                            suggested_actions=[],
                        ),
                    ],
                ),
            ],
        ),
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.meal_views_by_id[planned_meal_id] = meal_view
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, meal_view.meal_date)] = day_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = generation_context
    service = world.build_service(generation_client=generation_client)

    with pytest.raises(ValueError, match="другой день или слот"):
        await service.replan_meal(user.telegram_user_id, planned_meal_id)
