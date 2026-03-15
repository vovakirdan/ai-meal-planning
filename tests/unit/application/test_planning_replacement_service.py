# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.dto import (
    PlanConfirmationResult,
    StoredPlanningHousehold,
    StoredPlanningUser,
    StoredPlanReference,
)
from aimealplanner.application.planning.generation_dto import (
    DishQuickAction,
    PlanningMemberContext,
    RecipeHint,
    RecipeHintIngredient,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import (
    PlannedMealItemReplacement,
    ReplacementCandidate,
)
from aimealplanner.application.planning.replacement_service import DishReplacementService
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
    generation_contexts_by_plan_id: dict[UUID, WeeklyPlanGenerationContext] = field(
        default_factory=dict,
    )
    applied_replacements: list[PlannedMealItemReplacement] = field(default_factory=list)
    dish_ids_by_item_id: dict[UUID, UUID] = field(default_factory=dict)
    policies_by_dish_id: dict[UUID, DishFeedbackVerdict] = field(default_factory=dict)

    async def get_latest_draft_for_household(self, household_id: UUID) -> None:
        _ = household_id
        raise NotImplementedError

    async def get_latest_confirmed_for_household(
        self,
        household_id: UUID,
    ) -> StoredPlanReference | None:
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

    async def update_item_snapshot(self, replacement: PlannedMealItemReplacement) -> None:
        existing_item = self.item_views_by_id[replacement.planned_meal_item_id]
        self.applied_replacements.append(replacement)
        self.item_views_by_id[replacement.planned_meal_item_id] = StoredPlanItemView(
            weekly_plan_id=existing_item.weekly_plan_id,
            planned_meal_id=existing_item.planned_meal_id,
            planned_meal_item_id=existing_item.planned_meal_item_id,
            dish_id=None if replacement.clear_dish_link else existing_item.dish_id,
            meal_date=existing_item.meal_date,
            slot=existing_item.slot,
            name=replacement.name,
            summary=replacement.summary,
            adaptation_notes=replacement.adaptation_notes,
            snapshot_payload=replacement.snapshot_payload,
            suggested_actions=_extract_test_quick_actions(replacement.snapshot_payload),
            household_policy_verdict=None,
            household_policy_note=None,
        )

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
            household_policy_verdict=self.policies_by_dish_id.get(dish_id),
            household_policy_note=None,
        )
        return dish_id

    async def upsert_household_dish_policy(
        self,
        household_id: UUID,
        dish_id: UUID,
        verdict: DishFeedbackVerdict,
        note: str | None,
    ) -> None:
        _ = (household_id, note)
        self.policies_by_dish_id[dish_id] = verdict
        for item_id, current_dish_id in list(self.dish_ids_by_item_id.items()):
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
    ) -> PlanConfirmationResult:
        _ = (household_id, weekly_plan_id, confirmed_at)
        raise NotImplementedError


@dataclass
class FakeSuggestionClient:
    result: list[ReplacementCandidate]
    adjustment_result: ReplacementCandidate | None = None
    observed_item_name: str | None = None
    observed_reference_titles: list[str] = field(default_factory=list)
    observed_adjustment_instruction: str | None = None

    async def suggest_replacements(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        reference_recipes: list[RecipeHint],
    ) -> list[ReplacementCandidate]:
        _ = generation_context
        self.observed_item_name = item_view.name
        self.observed_reference_titles = [recipe.title for recipe in reference_recipes]
        return self.result

    async def adjust_item(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        instruction: str,
        reference_recipes: list[RecipeHint],
    ) -> ReplacementCandidate:
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
        suggestion_client: FakeSuggestionClient,
        recipe_hint_provider: FakeRecipeHintProvider | None = None,
    ) -> DishReplacementService:
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
        return DishReplacementService(
            session_factory,
            repositories_factory,
            suggestion_client=suggestion_client,
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


def _build_item_view(weekly_plan_id: UUID, planned_meal_item_id: UUID) -> StoredPlanItemView:
    return StoredPlanItemView(
        weekly_plan_id=weekly_plan_id,
        planned_meal_id=uuid4(),
        planned_meal_item_id=planned_meal_item_id,
        dish_id=None,
        meal_date=date(2026, 3, 23),
        slot="dinner",
        name="Паста с курицей",
        summary="Сливочная паста на ужин",
        adaptation_notes=["меньше чеснока"],
        snapshot_payload={"summary": "Сливочная паста на ужин"},
        suggested_actions=[
            DishQuickAction(
                label="Легче",
                instruction="Сделай блюдо легче.",
            ),
            DishQuickAction(
                label="Мягче вкус",
                instruction="Сделай вкус мягче.",
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
        week_mood="Средиземноморская",
        weekly_notes="побольше быстрых ужинов",
        pantry_considered=True,
        context_payload={"source": "test"},
        members=[
            PlanningMemberContext(
                display_name="Вова",
                constraints=["без оливок"],
                favorite_cuisines=["итальянская"],
                profile_note=None,
            ),
        ],
        pantry_items=[],
    )


def _build_recipe_hint() -> RecipeHint:
    return RecipeHint(
        provider="spoonacular",
        external_id="123",
        title="Creamy Chicken Pasta",
        source_url=None,
        cuisines=["Italian"],
        diets=[],
        summary="Quick creamy pasta.",
        ready_in_minutes=25,
        servings=2,
        ingredients=[
            RecipeHintIngredient(name="pasta", amount="200 g"),
            RecipeHintIngredient(name="chicken", amount="300 g"),
        ],
    )


@pytest.mark.asyncio
async def test_suggest_replacements_uses_recipe_hints_when_available() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_item_id = uuid4()
    item_view = _build_item_view(weekly_plan_id, planned_meal_item_id)
    generation_context = _build_generation_context(weekly_plan_id, household.id)
    recipe_hint = _build_recipe_hint()
    suggestion_client = FakeSuggestionClient(
        result=[
            ReplacementCandidate(
                name="Запеченная рыба с картофелем",
                summary="Спокойный ужин без лишней тяжести",
                adaptation_notes=["без оливок"],
                suggested_actions=[],
                reason="Лучше подходит под семейные ограничения",
            ),
            ReplacementCandidate(
                name="Индейка с булгуром",
                summary="Сытный, но более легкий семейный ужин",
                adaptation_notes=["без оливок"],
                suggested_actions=[],
                reason="Удобно готовить на несколько порций",
            ),
            ReplacementCandidate(
                name="Курица с запеченными овощами",
                summary="Привычный будничный вариант без лишней сложности",
                adaptation_notes=["без оливок"],
                suggested_actions=[],
                reason="Сохраняет формат простого домашнего ужина",
            ),
        ],
    )
    recipe_hint_provider = FakeRecipeHintProvider(result=[recipe_hint])
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = item_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = generation_context
    service = world.build_service(
        suggestion_client=suggestion_client,
        recipe_hint_provider=recipe_hint_provider,
    )

    result = await service.suggest_replacements(user.telegram_user_id, planned_meal_item_id)

    assert recipe_hint_provider.observed_queries == ["Паста с курицей"]
    assert suggestion_client.observed_item_name == "Паста с курицей"
    assert suggestion_client.observed_reference_titles == ["Creamy Chicken Pasta"]
    assert result.reference_recipes == [recipe_hint]
    assert len(result.candidates) == 3


@pytest.mark.asyncio
async def test_apply_replacement_updates_item_snapshot_and_commits() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_item_id = uuid4()
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = _build_item_view(
        weekly_plan_id,
        planned_meal_item_id,
    )
    suggestion_client = FakeSuggestionClient(result=[])
    service = world.build_service(suggestion_client=suggestion_client)

    result = await service.apply_replacement(
        user.telegram_user_id,
        PlannedMealItemReplacement(
            planned_meal_item_id=planned_meal_item_id,
            name="Индейка с булгуром",
            summary="Более легкий ужин на каждый день",
            adaptation_notes=["без оливок", "меньше масла"],
            snapshot_payload={
                "summary": "Более легкий ужин на каждый день",
                "generation_source": "ai_replacement",
            },
        ),
    )

    assert world.session.commit_count == 1
    assert world.weekly_plan_repository.applied_replacements[0].name == "Индейка с булгуром"
    assert result.updated_item.name == "Индейка с булгуром"
    assert result.updated_item.adaptation_notes == ["без оливок", "меньше масла"]
    assert result.updated_item.dish_id is None


@pytest.mark.asyncio
async def test_apply_adjustment_updates_item_in_place_and_keeps_instruction() -> None:
    world = FakePlanningWorld()
    user, household = _build_user_and_household()
    weekly_plan_id = uuid4()
    planned_meal_item_id = uuid4()
    item_view = _build_item_view(weekly_plan_id, planned_meal_item_id)
    generation_context = _build_generation_context(weekly_plan_id, household.id)
    suggestion_client = FakeSuggestionClient(
        result=[],
        adjustment_result=ReplacementCandidate(
            name="Паста с курицей",
            summary="Менее острая и более мягкая версия ужина",
            adaptation_notes=["меньше острого перца"],
            suggested_actions=[],
            reason="Убрал остроту и сделал вкус мягче",
        ),
    )
    world.user_repository.users_by_tg_id[user.telegram_user_id] = user
    world.household_repository.households_by_user_id[user.id] = household
    world.weekly_plan_repository.item_views_by_id[planned_meal_item_id] = item_view
    world.weekly_plan_repository.generation_contexts_by_plan_id[weekly_plan_id] = generation_context
    service = world.build_service(suggestion_client=suggestion_client)

    result = await service.apply_adjustment(
        user.telegram_user_id,
        planned_meal_item_id,
        "Сделай блюдо менее острым.",
        generation_source="ai_adjustment:custom",
    )

    assert world.session.commit_count == 1
    assert suggestion_client.observed_adjustment_instruction == "Сделай блюдо менее острым."
    assert result.updated_item.summary == "Менее острая и более мягкая версия ужина"
    assert result.updated_item.adaptation_notes == ["меньше острого перца"]
    assert result.updated_item.dish_id is None
    assert result.updated_item.snapshot_payload["adjustment_instruction"] == (
        "Сделай блюдо менее острым."
    )


def _extract_test_quick_actions(snapshot_payload: dict[str, object]) -> list[DishQuickAction]:
    payload = snapshot_payload.get("suggested_actions")
    if not isinstance(payload, list):
        return []
    actions: list[DishQuickAction] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        item_payload = cast(dict[str, object], item)
        label = item_payload.get("label")
        instruction = item_payload.get("instruction")
        if not isinstance(label, str) or not isinstance(instruction, str):
            continue
        actions.append(DishQuickAction(label=label, instruction=instruction))
    return actions
