# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
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
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
    WeeklyPlanRepository,
)
from aimealplanner.application.planning.shopping_dto import (
    ShoppingListItemDraft,
    ShoppingListResult,
    ShoppingSourceContext,
    ShoppingSourceIngredientEntry,
    ShoppingSourcePantryEntry,
)
from aimealplanner.application.planning.shopping_service import (
    RecipeWarmupClient,
    ShoppingListService,
    render_shopping_list,
)
from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    PantryStockLevel,
    RepeatabilityMode,
    ShoppingListAvailabilityStatus,
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
    latest_draft_by_household_id: dict[UUID, StoredDraftPlan] = field(default_factory=dict)
    latest_confirmed_by_household_id: dict[UUID, StoredPlanReference] = field(default_factory=dict)
    shopping_sources_by_plan_id: dict[UUID, ShoppingSourceContext] = field(default_factory=dict)
    shopping_sources_queue_by_plan_id: dict[UUID, list[ShoppingSourceContext]] = field(
        default_factory=dict,
    )
    created_results_by_plan_id: dict[UUID, ShoppingListResult] = field(default_factory=dict)
    created_items_by_plan_id: dict[UUID, list[ShoppingListItemDraft]] = field(default_factory=dict)

    async def get_latest_draft_for_household(self, household_id: UUID) -> StoredDraftPlan | None:
        return self.latest_draft_by_household_id.get(household_id)

    async def get_latest_confirmed_for_household(
        self,
        household_id: UUID,
    ) -> StoredPlanReference | None:
        return self.latest_confirmed_by_household_id.get(household_id)

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

    async def get_item_view(self, household_id: UUID, planned_meal_item_id: UUID) -> None:
        _ = (household_id, planned_meal_item_id)
        raise NotImplementedError

    async def update_item_snapshot(self, replacement: object) -> None:
        _ = replacement
        raise NotImplementedError

    async def ensure_item_dish(self, household_id: UUID, planned_meal_item_id: UUID) -> UUID:
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

    async def get_generation_context(self, weekly_plan_id: UUID) -> None:
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

    async def get_shopping_source(
        self,
        household_id: UUID,
        weekly_plan_id: UUID,
    ) -> ShoppingSourceContext | None:
        _ = household_id
        queued_sources = self.shopping_sources_queue_by_plan_id.get(weekly_plan_id)
        if queued_sources:
            return queued_sources.pop(0)
        return self.shopping_sources_by_plan_id.get(weekly_plan_id)

    async def create_shopping_list(
        self,
        weekly_plan_id: UUID,
        items: list[ShoppingListItemDraft],
    ) -> ShoppingListResult:
        self.created_items_by_plan_id[weekly_plan_id] = items
        return self.created_results_by_plan_id[weekly_plan_id]


def _build_service(
    user_repository: FakePlanningUserRepository,
    household_repository: FakePlanningHouseholdRepository,
    weekly_plan_repository: FakeWeeklyPlanRepository,
    *,
    session: FakeSession | None = None,
    recipe_warmer: RecipeWarmupClient | None = None,
) -> ShoppingListService:
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        FakeSessionFactory(session or FakeSession()),
    )
    repositories_factory = cast(
        PlanningRepositoryBundleFactory,
        lambda _session: PlanningRepositories(
            user_repository=user_repository,
            household_repository=household_repository,
            weekly_plan_repository=cast(WeeklyPlanRepository, weekly_plan_repository),
        ),
    )
    return ShoppingListService(
        session_factory,
        repositories_factory,
        recipe_warmer=recipe_warmer,
    )


@dataclass
class FakeRecipeWarmer:
    warm_calls: list[tuple[int, UUID]] = field(default_factory=list)

    async def warm_plan_recipes(self, telegram_user_id: int, weekly_plan_id: UUID) -> int:
        self.warm_calls.append((telegram_user_id, weekly_plan_id))
        return 1


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
            pantry_items_count=3,
        ),
    )


@pytest.mark.asyncio
async def test_generate_for_latest_visible_week_uses_draft_and_aggregates_items() -> None:
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    draft_plan = StoredDraftPlan(
        id=uuid4(),
        start_date=date(2026, 3, 16),
        end_date=date(2026, 3, 22),
    )
    confirmed_plan = StoredPlanReference(
        id=uuid4(),
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 15),
        status=WeeklyPlanStatus.CONFIRMED,
    )
    weekly_plan_repository.latest_draft_by_household_id[household.id] = draft_plan
    weekly_plan_repository.latest_confirmed_by_household_id[household.id] = confirmed_plan
    ingredient_id_tofu = uuid4()
    ingredient_id_rice = uuid4()
    weekly_plan_repository.shopping_sources_by_plan_id[draft_plan.id] = ShoppingSourceContext(
        weekly_plan_id=draft_plan.id,
        start_date=draft_plan.start_date,
        end_date=draft_plan.end_date,
        ingredient_entries=[
            ShoppingSourceIngredientEntry(
                ingredient_id=ingredient_id_tofu,
                canonical_name="Тофу",
                shopping_category="Холодильник",
                default_unit="г",
                amount_text="300 г",
                quantity_value=None,
                quantity_unit=None,
                preparation_note=None,
                dish_name="Пад тай",
            ),
            ShoppingSourceIngredientEntry(
                ingredient_id=ingredient_id_tofu,
                canonical_name="Тофу",
                shopping_category="Холодильник",
                default_unit="г",
                amount_text="200 г",
                quantity_value=None,
                quantity_unit=None,
                preparation_note="нарезать кубиками",
                dish_name="Боул",
            ),
            ShoppingSourceIngredientEntry(
                ingredient_id=ingredient_id_rice,
                canonical_name="Рис",
                shopping_category="Бакалея",
                default_unit="г",
                amount_text="500 г",
                quantity_value=Decimal("500"),
                quantity_unit="г",
                preparation_note=None,
                dish_name="Боул",
            ),
        ],
        pantry_entries=[
            ShoppingSourcePantryEntry(
                ingredient_id=ingredient_id_tofu,
                stock_level=PantryStockLevel.LOW,
                quantity_value=None,
                quantity_unit=None,
                note=None,
            ),
            ShoppingSourcePantryEntry(
                ingredient_id=ingredient_id_rice,
                stock_level=PantryStockLevel.HAS,
                quantity_value=None,
                quantity_unit=None,
                note=None,
            ),
        ],
    )
    weekly_plan_repository.created_results_by_plan_id[draft_plan.id] = ShoppingListResult(
        shopping_list_id=uuid4(),
        weekly_plan_id=draft_plan.id,
        version=1,
        start_date=draft_plan.start_date,
        end_date=draft_plan.end_date,
        items=[],
    )
    service = _build_service(
        user_repository,
        household_repository,
        weekly_plan_repository,
        session=session,
    )

    result = await service.generate_for_latest_visible_week(user.telegram_user_id)

    created_items = weekly_plan_repository.created_items_by_plan_id[draft_plan.id]
    assert result.weekly_plan_id == draft_plan.id
    assert session.commit_count == 1
    assert [item.display_name for item in created_items] == ["Рис", "Тофу"]
    assert created_items[0].availability_status is ShoppingListAvailabilityStatus.PARTIALLY_HAVE
    assert created_items[0].quantity_label == "500 г"
    assert created_items[0].note is None
    assert created_items[1].availability_status is ShoppingListAvailabilityStatus.PARTIALLY_HAVE


@pytest.mark.asyncio
async def test_generate_for_latest_visible_week_falls_back_to_confirmed_plan() -> None:
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    confirmed_plan = StoredPlanReference(
        id=uuid4(),
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 15),
        status=WeeklyPlanStatus.CONFIRMED,
    )
    weekly_plan_repository.latest_confirmed_by_household_id[household.id] = confirmed_plan
    weekly_plan_repository.shopping_sources_by_plan_id[confirmed_plan.id] = ShoppingSourceContext(
        weekly_plan_id=confirmed_plan.id,
        start_date=confirmed_plan.start_date,
        end_date=confirmed_plan.end_date,
        ingredient_entries=[
            ShoppingSourceIngredientEntry(
                ingredient_id=uuid4(),
                canonical_name="Помидоры",
                shopping_category="Овощи",
                default_unit="шт",
                amount_text="2 шт",
                quantity_value=None,
                quantity_unit=None,
                preparation_note=None,
                dish_name="Салат",
            ),
        ],
        pantry_entries=[],
    )
    weekly_plan_repository.created_results_by_plan_id[confirmed_plan.id] = ShoppingListResult(
        shopping_list_id=uuid4(),
        weekly_plan_id=confirmed_plan.id,
        version=2,
        start_date=confirmed_plan.start_date,
        end_date=confirmed_plan.end_date,
        items=[],
    )
    service = _build_service(
        user_repository,
        household_repository,
        weekly_plan_repository,
        session=session,
    )

    result = await service.generate_for_latest_visible_week(user.telegram_user_id)

    assert result.weekly_plan_id == confirmed_plan.id
    created_items = weekly_plan_repository.created_items_by_plan_id[confirmed_plan.id]
    assert created_items[0].availability_status is ShoppingListAvailabilityStatus.NEED_TO_BUY
    assert created_items[0].quantity_label == "2 шт"


def test_render_shopping_list_groups_items_by_availability() -> None:
    result = ShoppingListResult(
        shopping_list_id=uuid4(),
        weekly_plan_id=uuid4(),
        version=1,
        start_date=date(2026, 3, 16),
        end_date=date(2026, 3, 22),
        items=[
            ShoppingListItemDraft(
                ingredient_id=uuid4(),
                display_name="Тофу",
                quantity_value=Decimal("500"),
                quantity_unit="г",
                category="Холодильник",
                availability_status=ShoppingListAvailabilityStatus.NEED_TO_BUY,
                note=None,
                quantity_label="500 г",
            ),
            ShoppingListItemDraft(
                ingredient_id=uuid4(),
                display_name="Рис",
                quantity_value=Decimal("300"),
                quantity_unit="г",
                category="Бакалея",
                availability_status=ShoppingListAvailabilityStatus.PARTIALLY_HAVE,
                note=None,
                quantity_label="300 г",
            ),
        ],
    )

    rendered = render_shopping_list(result)

    assert "Купить:" in rendered
    assert "- Тофу — 500 г" in rendered
    assert "Проверить дома:" in rendered
    assert "- Рис — 300 г" in rendered


@pytest.mark.asyncio
async def test_generate_for_latest_visible_week_subtracts_known_pantry_quantity() -> None:
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    user, household = _build_user_and_household()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    draft_plan = StoredDraftPlan(
        id=uuid4(),
        start_date=date(2026, 3, 16),
        end_date=date(2026, 3, 22),
    )
    weekly_plan_repository.latest_draft_by_household_id[household.id] = draft_plan
    chicken_id = uuid4()
    weekly_plan_repository.shopping_sources_by_plan_id[draft_plan.id] = ShoppingSourceContext(
        weekly_plan_id=draft_plan.id,
        start_date=draft_plan.start_date,
        end_date=draft_plan.end_date,
        ingredient_entries=[
            ShoppingSourceIngredientEntry(
                ingredient_id=chicken_id,
                canonical_name="Курица",
                shopping_category="Холодильник",
                default_unit="г",
                amount_text="1000 г",
                quantity_value=None,
                quantity_unit=None,
                preparation_note=None,
                dish_name="Ужин 1",
            ),
            ShoppingSourceIngredientEntry(
                ingredient_id=chicken_id,
                canonical_name="Курица",
                shopping_category="Холодильник",
                default_unit="г",
                amount_text="500 г",
                quantity_value=None,
                quantity_unit=None,
                preparation_note=None,
                dish_name="Ужин 2",
            ),
        ],
        pantry_entries=[
            ShoppingSourcePantryEntry(
                ingredient_id=chicken_id,
                stock_level=PantryStockLevel.HAS,
                quantity_value=Decimal("300"),
                quantity_unit="г",
                note=None,
            ),
        ],
    )
    weekly_plan_repository.created_results_by_plan_id[draft_plan.id] = ShoppingListResult(
        shopping_list_id=uuid4(),
        weekly_plan_id=draft_plan.id,
        version=1,
        start_date=draft_plan.start_date,
        end_date=draft_plan.end_date,
        items=[],
    )
    service = _build_service(
        user_repository,
        household_repository,
        weekly_plan_repository,
        session=session,
    )

    await service.generate_for_latest_visible_week(user.telegram_user_id)

    created_items = weekly_plan_repository.created_items_by_plan_id[draft_plan.id]
    assert [item.display_name for item in created_items] == ["Курица"]
    assert created_items[0].availability_status is ShoppingListAvailabilityStatus.NEED_TO_BUY
    assert created_items[0].quantity_label == "1200 г"


@pytest.mark.asyncio
async def test_generate_for_latest_visible_week_warms_recipes_when_source_is_initially_empty() -> (
    None
):
    session = FakeSession()
    user_repository = FakePlanningUserRepository()
    household_repository = FakePlanningHouseholdRepository()
    weekly_plan_repository = FakeWeeklyPlanRepository()
    recipe_warmer = FakeRecipeWarmer()
    user, household = _build_user_and_household()
    user_repository.users_by_tg_id[user.telegram_user_id] = user
    household_repository.households_by_user_id[user.id] = household
    draft_plan = StoredDraftPlan(
        id=uuid4(),
        start_date=date(2026, 3, 16),
        end_date=date(2026, 3, 22),
    )
    weekly_plan_repository.latest_draft_by_household_id[household.id] = draft_plan
    weekly_plan_repository.shopping_sources_queue_by_plan_id[draft_plan.id] = [
        ShoppingSourceContext(
            weekly_plan_id=draft_plan.id,
            start_date=draft_plan.start_date,
            end_date=draft_plan.end_date,
            ingredient_entries=[],
            pantry_entries=[],
        ),
        ShoppingSourceContext(
            weekly_plan_id=draft_plan.id,
            start_date=draft_plan.start_date,
            end_date=draft_plan.end_date,
            ingredient_entries=[
                ShoppingSourceIngredientEntry(
                    ingredient_id=uuid4(),
                    canonical_name="Помидоры",
                    shopping_category="Овощи",
                    default_unit="шт",
                    amount_text="2 шт",
                    quantity_value=None,
                    quantity_unit=None,
                    preparation_note=None,
                    dish_name="Салат",
                ),
            ],
            pantry_entries=[],
        ),
    ]
    weekly_plan_repository.created_results_by_plan_id[draft_plan.id] = ShoppingListResult(
        shopping_list_id=uuid4(),
        weekly_plan_id=draft_plan.id,
        version=1,
        start_date=draft_plan.start_date,
        end_date=draft_plan.end_date,
        items=[],
    )
    service = _build_service(
        user_repository,
        household_repository,
        weekly_plan_repository,
        session=session,
        recipe_warmer=recipe_warmer,
    )

    result = await service.generate_for_latest_visible_week(user.telegram_user_id)

    assert result.weekly_plan_id == draft_plan.id
    assert recipe_warmer.warm_calls == [(user.telegram_user_id, draft_plan.id)]
    created_items = weekly_plan_repository.created_items_by_plan_id[draft_plan.id]
    assert created_items[0].display_name == "Помидоры"
