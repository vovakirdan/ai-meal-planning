# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
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
    RecipeHint,
    RecipeHintIngredient,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.recipe_dto import RecipeDetails, RecipeIngredient
from aimealplanner.application.planning.recipe_service import RecipeService
from aimealplanner.application.planning.replacement_dto import PlannedMealItemReplacement
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
class FakeWeeklyPlanRepository:
    latest_draft_by_household_id: dict[UUID, UUID] = field(default_factory=dict)
    latest_confirmed_by_household_id: dict[UUID, UUID] = field(default_factory=dict)
    overviews_by_plan_id: dict[UUID, StoredPlanOverview] = field(default_factory=dict)
    day_views_by_key: dict[tuple[UUID, date], StoredPlanDayView] = field(default_factory=dict)
    meal_views_by_id: dict[UUID, StoredPlanMealView] = field(default_factory=dict)
    item_views_by_id: dict[UUID, StoredPlanItemView] = field(default_factory=dict)
    generation_contexts_by_plan_id: dict[UUID, WeeklyPlanGenerationContext] = field(
        default_factory=dict,
    )
    applied_replacements: list[PlannedMealItemReplacement] = field(default_factory=list)

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

    async def get_latest_confirmed_for_household(
        self,
        household_id: UUID,
    ) -> StoredPlanReference | None:
        weekly_plan_id = self.latest_confirmed_by_household_id.get(household_id)
        if weekly_plan_id is None:
            return None
        overview = self.overviews_by_plan_id[weekly_plan_id]
        return StoredPlanReference(
            id=overview.weekly_plan_id,
            start_date=overview.start_date,
            end_date=overview.end_date,
            status=overview.status,
        )

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

    async def update_item_snapshot(self, replacement: PlannedMealItemReplacement) -> None:
        existing_item = self.item_views_by_id[replacement.planned_meal_item_id]
        self.applied_replacements.append(replacement)
        self.item_views_by_id[replacement.planned_meal_item_id] = StoredPlanItemView(
            weekly_plan_id=existing_item.weekly_plan_id,
            planned_meal_id=existing_item.planned_meal_id,
            planned_meal_item_id=existing_item.planned_meal_item_id,
            dish_id=existing_item.dish_id,
            meal_date=existing_item.meal_date,
            slot=existing_item.slot,
            name=replacement.name,
            summary=replacement.summary,
            adaptation_notes=replacement.adaptation_notes,
            snapshot_payload=replacement.snapshot_payload,
            suggested_actions=existing_item.suggested_actions,
            household_policy_verdict=existing_item.household_policy_verdict,
            household_policy_note=existing_item.household_policy_note,
        )

    async def ensure_item_dish(
        self,
        household_id: UUID,
        planned_meal_item_id: UUID,
    ) -> UUID:
        _ = (household_id, planned_meal_item_id)
        raise NotImplementedError

    async def upsert_household_dish_policy(
        self,
        household_id: UUID,
        dish_id: UUID,
        verdict: DishFeedbackVerdict,
        note: str | None,
    ) -> None:
        _ = (household_id, dish_id, verdict, note)
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


@dataclass
class FakeRecipeExpansionClient:
    result: RecipeDetails
    adjustment_result: RecipeDetails | None = None
    observed_item_name: str | None = None
    observed_reference_titles: list[str] = field(default_factory=list)
    observed_adjustment_instruction: str | None = None

    async def expand_item_recipe(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        reference_recipes: list[RecipeHint],
    ) -> RecipeDetails:
        _ = generation_context
        self.observed_item_name = item_view.name
        self.observed_reference_titles = [recipe.title for recipe in reference_recipes]
        return self.result

    async def adjust_item_recipe(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        instruction: str,
        reference_recipes: list[RecipeHint],
    ) -> RecipeDetails:
        _ = generation_context
        self.observed_item_name = item_view.name
        self.observed_reference_titles = [recipe.title for recipe in reference_recipes]
        self.observed_adjustment_instruction = instruction
        if self.adjustment_result is None:
            raise AssertionError("adjustment_result must be configured for this test")
        return self.adjustment_result


@dataclass
class FakeRecipeHintProvider:
    result: list[RecipeHint]
    observed_queries: list[str] = field(default_factory=list)

    async def collect_hints(self, context: WeeklyPlanGenerationContext) -> list[RecipeHint]:
        _ = context
        raise NotImplementedError

    async def search_related_recipes(
        self,
        query: str,
        context: WeeklyPlanGenerationContext,
    ) -> list[RecipeHint]:
        _ = context
        self.observed_queries.append(query)
        return self.result


@dataclass
class FakeRecipeWorld:
    session: FakeSession = field(default_factory=FakeSession)
    user_repository: FakePlanningUserRepository = field(default_factory=FakePlanningUserRepository)
    household_repository: FakePlanningHouseholdRepository = field(
        default_factory=FakePlanningHouseholdRepository,
    )
    weekly_plan_repository: FakeWeeklyPlanRepository = field(
        default_factory=FakeWeeklyPlanRepository,
    )


def _build_service(
    world: FakeRecipeWorld,
    recipe_client: FakeRecipeExpansionClient,
    *,
    recipe_hint_provider: FakeRecipeHintProvider | None = None,
) -> RecipeService:
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        FakeSessionFactory(world.session),
    )
    repositories_factory = cast(
        PlanningRepositoryBundleFactory,
        lambda _session: PlanningRepositories(
            user_repository=world.user_repository,
            household_repository=world.household_repository,
            weekly_plan_repository=cast(WeeklyPlanRepository, world.weekly_plan_repository),
        ),
    )
    return RecipeService(
        session_factory,
        repositories_factory,
        recipe_client=recipe_client,
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
            pantry_items_count=2,
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
        start_date=date(2026, 3, 16),
        end_date=date(2026, 3, 22),
        meal_count_per_day=3,
        desserts_enabled=False,
        repeatability_mode=RepeatabilityMode.BALANCED,
        active_slots=["breakfast", "lunch", "dinner"],
        week_mood="Азиатская",
        weekly_notes=None,
        pantry_considered=True,
        context_payload={"source": "test"},
        members=[],
        pantry_items=[],
    )


def _build_recipe_details() -> RecipeDetails:
    return RecipeDetails(
        summary="Домашняя версия блюда",
        ingredients=[
            RecipeIngredient(name="Тофу", amount="300 г", preparation_note="нарезать кубиками"),
            RecipeIngredient(name="Рисовая лапша", amount="200 г", preparation_note=None),
        ],
        preparation_steps=["Подготовить овощи и соус."],
        cooking_steps=["Быстро обжарить и соединить с лапшой."],
        serving_steps=["Подать сразу после готовности."],
        prep_time_minutes=15,
        cook_time_minutes=12,
        serving_notes="Сверху посыпать кунжутом.",
    )


def _build_recipe_hint() -> RecipeHint:
    return RecipeHint(
        provider="spoonacular",
        external_id="42",
        title="Pad Thai Reference",
        source_url=None,
        cuisines=["thai"],
        diets=[],
        summary="Reference summary",
        ready_in_minutes=25,
        servings=2,
        ingredients=[
            RecipeHintIngredient(name="Тофу", amount="300 г"),
            RecipeHintIngredient(name="Лапша", amount="200 г"),
        ],
    )


@pytest.mark.asyncio
async def test_get_start_context_filters_out_days_without_items() -> None:
    world = FakeRecipeWorld()
    user, household = _build_user_and_household()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    weekly_plan_id = uuid4()
    world.weekly_plan_repository.latest_draft_by_household_id[household.id] = weekly_plan_id
    world.weekly_plan_repository.overviews_by_plan_id[weekly_plan_id] = StoredPlanOverview(
        weekly_plan_id=weekly_plan_id,
        status=WeeklyPlanStatus.DRAFT,
        start_date=date(2026, 3, 16),
        end_date=date(2026, 3, 22),
        days=[
            StoredPlanDaySummary(
                meal_date=date(2026, 3, 16),
                meals_count=1,
                meals=[
                    StoredPlanMealSummary(
                        planned_meal_id=uuid4(),
                        slot="dinner",
                        note=None,
                        item_names=["Пад тай"],
                    ),
                ],
            ),
            StoredPlanDaySummary(
                meal_date=date(2026, 3, 17),
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
    service = _build_service(
        world,
        recipe_client=FakeRecipeExpansionClient(result=_build_recipe_details()),
    )

    context = await service.get_start_context(user.telegram_user_id)

    assert context.weekly_plan_id == weekly_plan_id
    assert [day.meal_date for day in context.days] == [date(2026, 3, 16)]
    assert context.days[0].items_count == 1


@pytest.mark.asyncio
async def test_get_day_context_collects_all_items_for_selected_day() -> None:
    world = FakeRecipeWorld()
    user, household = _build_user_and_household()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    weekly_plan_id = uuid4()
    breakfast_meal_id = uuid4()
    dinner_meal_id = uuid4()
    breakfast_item_id = uuid4()
    dinner_item_id = uuid4()
    meal_date = date(2026, 3, 16)
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, meal_date)] = StoredPlanDayView(
        weekly_plan_id=weekly_plan_id,
        meal_date=meal_date,
        meals=[
            StoredPlanMealSummary(
                planned_meal_id=breakfast_meal_id,
                slot="breakfast",
                note=None,
                item_names=["Овсянка"],
            ),
            StoredPlanMealSummary(
                planned_meal_id=dinner_meal_id,
                slot="dinner",
                note=None,
                item_names=["Пад тай"],
            ),
        ],
    )
    world.weekly_plan_repository.meal_views_by_id[breakfast_meal_id] = StoredPlanMealView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=breakfast_meal_id,
        meal_date=meal_date,
        slot="breakfast",
        note=None,
        items=[
            StoredMealItemSummary(
                planned_meal_item_id=breakfast_item_id,
                position=0,
                name="Овсянка",
            ),
        ],
    )
    world.weekly_plan_repository.meal_views_by_id[dinner_meal_id] = StoredPlanMealView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=dinner_meal_id,
        meal_date=meal_date,
        slot="dinner",
        note=None,
        items=[
            StoredMealItemSummary(
                planned_meal_item_id=dinner_item_id,
                position=0,
                name="Пад тай",
            ),
        ],
    )
    service = _build_service(
        world,
        recipe_client=FakeRecipeExpansionClient(result=_build_recipe_details()),
    )

    context = await service.get_day_context(
        user.telegram_user_id,
        weekly_plan_id=weekly_plan_id,
        meal_date=meal_date,
    )

    assert context.meal_date == meal_date
    assert [(item.slot, item.dish_name) for item in context.items] == [
        ("breakfast", "Овсянка"),
        ("dinner", "Пад тай"),
    ]


@pytest.mark.asyncio
async def test_get_item_with_recipe_skips_generation_for_existing_recipe_snapshot() -> None:
    world = FakeRecipeWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_item_id = uuid4()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = StoredPlanItemView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=uuid4(),
        planned_meal_item_id=planned_meal_item_id,
        dish_id=None,
        meal_date=date(2026, 3, 16),
        slot="dinner",
        name="Пад тай",
        summary="Кратко",
        adaptation_notes=["без лука"],
        snapshot_payload={
            "summary": "Кратко",
            "ingredients": [{"name": "Тофу", "amount": "300 г", "preparation_note": None}],
        },
        suggested_actions=[DishQuickAction(label="Мягче вкус", instruction="Сделай мягче.")],
        household_policy_verdict=None,
        household_policy_note=None,
    )
    recipe_client = FakeRecipeExpansionClient(result=_build_recipe_details())
    service = _build_service(world, recipe_client=recipe_client)

    result = await service.get_item_with_recipe(user.telegram_user_id, planned_meal_item_id)

    assert result.details_were_generated is False
    assert recipe_client.observed_item_name is None
    assert world.session.commit_count == 0
    assert world.weekly_plan_repository.applied_replacements == []


@pytest.mark.asyncio
async def test_get_item_with_recipe_generates_missing_details_and_persists_snapshot() -> None:
    world = FakeRecipeWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_item_id = uuid4()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = StoredPlanItemView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=uuid4(),
        planned_meal_item_id=planned_meal_item_id,
        dish_id=uuid4(),
        meal_date=date(2026, 3, 16),
        slot="dinner",
        name="Пад тай",
        summary="Быстрый ужин",
        adaptation_notes=["без лука"],
        snapshot_payload={
            "summary": "Быстрый ужин",
            "suggested_actions": [
                {"label": "Мягче вкус", "instruction": "Сделай вкус мягче."},
            ],
        },
        suggested_actions=[DishQuickAction(label="Мягче вкус", instruction="Сделай вкус мягче.")],
        household_policy_verdict=None,
        household_policy_note=None,
    )
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = (
        _build_generation_context(weekly_plan_id, household.id)
    )
    recipe_client = FakeRecipeExpansionClient(result=_build_recipe_details())
    hint_provider = FakeRecipeHintProvider(result=[_build_recipe_hint()])
    service = _build_service(
        world,
        recipe_client=recipe_client,
        recipe_hint_provider=hint_provider,
    )

    result = await service.get_item_with_recipe(user.telegram_user_id, planned_meal_item_id)

    assert result.details_were_generated is True
    assert recipe_client.observed_item_name == "Пад тай"
    assert recipe_client.observed_reference_titles == ["Pad Thai Reference"]
    assert hint_provider.observed_queries == ["Пад тай"]
    assert world.session.commit_count == 1
    assert len(world.weekly_plan_repository.applied_replacements) == 1
    applied_replacement = world.weekly_plan_repository.applied_replacements[0]
    assert applied_replacement.clear_dish_link is False
    assert applied_replacement.summary == "Домашняя версия блюда"
    assert result.item_view.snapshot_payload["ingredients"][0]["name"] == "Тофу"
    assert result.item_view.snapshot_payload["preparation_steps"] == ["Подготовить овощи и соус."]


@pytest.mark.asyncio
async def test_adjust_item_recipe_updates_saved_snapshot_from_feedback() -> None:
    world = FakeRecipeWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_item_id = uuid4()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = StoredPlanItemView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=uuid4(),
        planned_meal_item_id=planned_meal_item_id,
        dish_id=uuid4(),
        meal_date=date(2026, 3, 16),
        slot="dinner",
        name="Пад тай",
        summary="Старый рецепт",
        adaptation_notes=["без лука"],
        snapshot_payload={
            "summary": "Старый рецепт",
            "ingredients": [{"name": "Тофу", "amount": "200 г", "preparation_note": None}],
        },
        suggested_actions=[],
        household_policy_verdict=None,
        household_policy_note=None,
    )
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = (
        _build_generation_context(weekly_plan_id, household.id)
    )
    recipe_client = FakeRecipeExpansionClient(
        result=_build_recipe_details(),
        adjustment_result=RecipeDetails(
            summary="Обновленная версия",
            ingredients=[
                RecipeIngredient(name="Тофу", amount="250 г", preparation_note=None),
                RecipeIngredient(name="Соус", amount="4 ст. л.", preparation_note=None),
            ],
            preparation_steps=["Сначала смешать соус."],
            cooking_steps=["Потом быстро обжарить."],
            serving_steps=["Подать горячим."],
            prep_time_minutes=10,
            cook_time_minutes=8,
            serving_notes="Добавить лайм.",
        ),
    )
    hint_provider = FakeRecipeHintProvider(result=[_build_recipe_hint()])
    service = _build_service(
        world,
        recipe_client=recipe_client,
        recipe_hint_provider=hint_provider,
    )

    result = await service.adjust_item_recipe(
        user.telegram_user_id,
        planned_meal_item_id,
        "Сначала смешай соус, потом уже обжаривай.",
    )

    assert result.details_were_generated is True
    assert recipe_client.observed_adjustment_instruction == (
        "Сначала смешай соус, потом уже обжаривай."
    )
    assert result.item_view.snapshot_payload["recipe_feedback_note"] == (
        "Сначала смешай соус, потом уже обжаривай."
    )
    assert result.item_view.snapshot_payload["recipe_generation_source"] == "ai_recipe_feedback"
    assert result.item_view.snapshot_payload["cooking_steps"] == ["Потом быстро обжарить."]
    assert world.session.commit_count == 1


@pytest.mark.asyncio
async def test_warm_plan_recipes_generates_only_missing_recipe_snapshots() -> None:
    world = FakeRecipeWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    meal_date = date(2026, 3, 16)
    planned_meal_id = uuid4()
    missing_item_id = uuid4()
    ready_item_id = uuid4()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.overviews_by_plan_id[weekly_plan_id] = StoredPlanOverview(
        weekly_plan_id=weekly_plan_id,
        status=WeeklyPlanStatus.CONFIRMED,
        start_date=meal_date,
        end_date=meal_date,
        days=[
            StoredPlanDaySummary(
                meal_date=meal_date,
                meals_count=1,
                meals=[
                    StoredPlanMealSummary(
                        planned_meal_id=planned_meal_id,
                        slot="dinner",
                        note=None,
                        item_names=["Пад тай", "Салат"],
                    ),
                ],
            ),
        ],
    )
    world.weekly_plan_repository.day_views_by_key[(weekly_plan_id, meal_date)] = StoredPlanDayView(
        weekly_plan_id=weekly_plan_id,
        meal_date=meal_date,
        meals=[
            StoredPlanMealSummary(
                planned_meal_id=planned_meal_id,
                slot="dinner",
                note=None,
                item_names=["Пад тай", "Салат"],
            ),
        ],
    )
    world.weekly_plan_repository.meal_views_by_id[planned_meal_id] = StoredPlanMealView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=planned_meal_id,
        meal_date=meal_date,
        slot="dinner",
        note=None,
        items=[
            StoredMealItemSummary(
                planned_meal_item_id=missing_item_id,
                position=0,
                name="Пад тай",
            ),
            StoredMealItemSummary(
                planned_meal_item_id=ready_item_id,
                position=1,
                name="Салат",
            ),
        ],
    )
    world.weekly_plan_repository.item_views_by_id[missing_item_id] = StoredPlanItemView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=planned_meal_id,
        planned_meal_item_id=missing_item_id,
        dish_id=None,
        meal_date=meal_date,
        slot="dinner",
        name="Пад тай",
        summary="Без рецепта",
        adaptation_notes=[],
        snapshot_payload={"summary": "Без рецепта"},
        suggested_actions=[],
        household_policy_verdict=None,
        household_policy_note=None,
    )
    world.weekly_plan_repository.item_views_by_id[ready_item_id] = StoredPlanItemView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=planned_meal_id,
        planned_meal_item_id=ready_item_id,
        dish_id=None,
        meal_date=meal_date,
        slot="dinner",
        name="Салат",
        summary="С рецептом",
        adaptation_notes=[],
        snapshot_payload={
            "summary": "С рецептом",
            "ingredients": [{"name": "Огурец", "amount": "1 шт", "preparation_note": None}],
        },
        suggested_actions=[],
        household_policy_verdict=None,
        household_policy_note=None,
    )
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = (
        _build_generation_context(weekly_plan_id, household.id)
    )
    recipe_client = FakeRecipeExpansionClient(result=_build_recipe_details())
    hint_provider = FakeRecipeHintProvider(result=[_build_recipe_hint()])
    service = _build_service(
        world,
        recipe_client=recipe_client,
        recipe_hint_provider=hint_provider,
    )

    generated_count = await service.warm_plan_recipes(
        user.telegram_user_id,
        weekly_plan_id,
    )

    assert generated_count == 1
    assert recipe_client.observed_item_name == "Пад тай"
    assert (
        world.weekly_plan_repository.item_views_by_id[missing_item_id].snapshot_payload[
            "ingredients"
        ][0]["name"]
        == "Тофу"
    )
    assert world.session.commit_count == 1
