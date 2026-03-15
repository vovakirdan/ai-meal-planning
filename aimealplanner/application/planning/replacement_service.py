# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.generation_dto import (
    RecipeHint,
    RecipeHintProvider,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import (
    PlannedMealItemReplacement,
    ReplacementCandidate,
    ReplacementSuggestionResult,
)
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)


class ReplacementSuggestionClient(Protocol):
    async def suggest_replacements(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        reference_recipes: list[RecipeHint],
    ) -> list[ReplacementCandidate]: ...


@dataclass(frozen=True, slots=True)
class ReplacementApplyResult:
    updated_item: StoredPlanItemView


class DishReplacementService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        suggestion_client: ReplacementSuggestionClient,
        recipe_hint_provider: RecipeHintProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._suggestion_client = suggestion_client
        self._recipe_hint_provider = recipe_hint_provider

    async def suggest_replacements(
        self,
        telegram_user_id: int,
        planned_meal_item_id: UUID,
    ) -> ReplacementSuggestionResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)

            item_view = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                planned_meal_item_id,
            )
            if item_view is None:
                raise ValueError("Не удалось открыть выбранное блюдо.")

            generation_context = await repositories.weekly_plan_repository.get_generation_context(
                item_view.weekly_plan_id,
            )
            if generation_context is None:
                raise ValueError("Не удалось восстановить контекст недельного плана.")

            reference_recipes = await _collect_reference_recipes(
                self._recipe_hint_provider,
                generation_context,
                item_view.name,
            )
            candidates = await self._suggestion_client.suggest_replacements(
                item_view=item_view,
                generation_context=generation_context,
                reference_recipes=reference_recipes,
            )
            return ReplacementSuggestionResult(
                item_view=item_view,
                generation_context=generation_context,
                candidates=candidates,
                reference_recipes=reference_recipes,
            )

    async def apply_replacement(
        self,
        telegram_user_id: int,
        replacement: PlannedMealItemReplacement,
    ) -> ReplacementApplyResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            existing_item = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                replacement.planned_meal_item_id,
            )
            if existing_item is None:
                raise ValueError("Не удалось открыть выбранное блюдо.")

            await repositories.weekly_plan_repository.update_item_snapshot(replacement)
            await session.commit()

            updated_item = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                replacement.planned_meal_item_id,
            )
            if updated_item is None:
                raise ValueError("Не удалось прочитать обновленное блюдо.")

            return ReplacementApplyResult(updated_item=updated_item)


async def _resolve_household_id(
    repositories: PlanningRepositories,
    telegram_user_id: int,
) -> UUID:
    user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
    if user is None:
        raise ValueError("Профиль не найден. Сначала отправь /start.")

    household = await repositories.household_repository.get_by_user_id(user.id)
    if household is None or household.onboarding_completed_at is None:
        raise ValueError("Сначала заверши стартовую настройку через /start.")
    return household.id


async def _collect_reference_recipes(
    recipe_hint_provider: RecipeHintProvider | None,
    generation_context: WeeklyPlanGenerationContext,
    dish_name: str,
) -> list[RecipeHint]:
    if recipe_hint_provider is None:
        return []
    return await recipe_hint_provider.search_related_recipes(dish_name, generation_context)
