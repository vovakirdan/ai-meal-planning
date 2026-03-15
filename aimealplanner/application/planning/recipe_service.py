# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.dto import StoredDraftPlan, StoredPlanReference
from aimealplanner.application.planning.generation_dto import (
    RecipeHint,
    RecipeHintProvider,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.recipe_dto import (
    RecipeDayContext,
    RecipeDayOption,
    RecipeDetails,
    RecipeItemOption,
    RecipeStartContext,
)
from aimealplanner.application.planning.replacement_dto import PlannedMealItemReplacement
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)


class RecipeExpansionClient(Protocol):
    async def expand_item_recipe(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        reference_recipes: list[RecipeHint],
    ) -> RecipeDetails: ...

    async def adjust_item_recipe(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        instruction: str,
        reference_recipes: list[RecipeHint],
    ) -> RecipeDetails: ...


@dataclass(frozen=True, slots=True)
class RecipeItemResult:
    item_view: StoredPlanItemView
    details_were_generated: bool


class RecipeService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        *,
        recipe_client: RecipeExpansionClient,
        recipe_hint_provider: RecipeHintProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._recipe_client = recipe_client
        self._recipe_hint_provider = recipe_hint_provider

    async def get_start_context(self, telegram_user_id: int) -> RecipeStartContext:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            plan_reference = await _resolve_latest_visible_plan(repositories, household_id)
            if plan_reference is None:
                raise ValueError("Текущего плана пока нет. Сначала составь его через /plan.")

            overview = await repositories.weekly_plan_repository.get_plan_overview(
                household_id,
                plan_reference.id,
            )
            if overview is None:
                raise ValueError("Не удалось открыть текущую неделю.")

            days = [
                RecipeDayOption(
                    meal_date=day.meal_date,
                    items_count=sum(len(meal.item_names) for meal in day.meals),
                )
                for day in overview.days
                if any(meal.item_names for meal in day.meals)
            ]
            if not days:
                raise ValueError("В текущей неделе пока нет блюд.")

            return RecipeStartContext(
                weekly_plan_id=overview.weekly_plan_id,
                status=overview.status,
                start_date=overview.start_date,
                end_date=overview.end_date,
                days=days,
            )

    async def get_day_context(
        self,
        telegram_user_id: int,
        *,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> RecipeDayContext:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            day_view = await repositories.weekly_plan_repository.get_day_view(
                household_id,
                weekly_plan_id,
                meal_date,
            )
            if day_view is None:
                raise ValueError("Не удалось открыть выбранный день.")

            items: list[RecipeItemOption] = []
            for meal in day_view.meals:
                meal_view = await repositories.weekly_plan_repository.get_meal_view(
                    household_id,
                    meal.planned_meal_id,
                )
                if meal_view is None:
                    continue
                items.extend(
                    [
                        RecipeItemOption(
                            planned_meal_item_id=item.planned_meal_item_id,
                            meal_date=meal_view.meal_date,
                            slot=meal_view.slot,
                            dish_name=item.name,
                        )
                        for item in meal_view.items
                    ],
                )

            if not items:
                raise ValueError("На этот день пока нет блюд.")

            return RecipeDayContext(
                weekly_plan_id=weekly_plan_id,
                meal_date=meal_date,
                items=items,
            )

    async def get_item_with_recipe(
        self,
        telegram_user_id: int,
        planned_meal_item_id: UUID,
    ) -> RecipeItemResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            item_view = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                planned_meal_item_id,
            )
            if item_view is None:
                raise ValueError("Не удалось открыть выбранное блюдо.")

            if _has_recipe_details(item_view):
                return RecipeItemResult(item_view=item_view, details_were_generated=False)

            updated_item = await self._generate_and_persist_recipe(
                repositories,
                household_id=household_id,
                item_view=item_view,
                generation_instruction=None,
            )
            await session.commit()
            return RecipeItemResult(item_view=updated_item, details_were_generated=True)

    async def adjust_item_recipe(
        self,
        telegram_user_id: int,
        planned_meal_item_id: UUID,
        instruction: str,
    ) -> RecipeItemResult:
        normalized_instruction = instruction.strip()
        if not normalized_instruction:
            raise ValueError("Нужно написать, что именно поправить в рецепте.")

        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            item_view = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                planned_meal_item_id,
            )
            if item_view is None:
                raise ValueError("Не удалось открыть выбранное блюдо.")

            updated_item = await self._generate_and_persist_recipe(
                repositories,
                household_id=household_id,
                item_view=item_view,
                generation_instruction=normalized_instruction,
            )
            await session.commit()
            return RecipeItemResult(item_view=updated_item, details_were_generated=True)

    async def warm_plan_recipes(
        self,
        telegram_user_id: int,
        weekly_plan_id: UUID,
    ) -> int:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            overview = await repositories.weekly_plan_repository.get_plan_overview(
                household_id,
                weekly_plan_id,
            )
            if overview is None:
                raise ValueError("Не удалось открыть выбранную неделю.")

            generated_count = 0
            for day in overview.days:
                day_view = await repositories.weekly_plan_repository.get_day_view(
                    household_id,
                    weekly_plan_id,
                    day.meal_date,
                )
                if day_view is None:
                    continue
                for meal in day_view.meals:
                    meal_view = await repositories.weekly_plan_repository.get_meal_view(
                        household_id,
                        meal.planned_meal_id,
                    )
                    if meal_view is None:
                        continue
                    for item in meal_view.items:
                        item_view = await repositories.weekly_plan_repository.get_item_view(
                            household_id,
                            item.planned_meal_item_id,
                        )
                        if item_view is None or _has_recipe_details(item_view):
                            continue
                        await self._generate_and_persist_recipe(
                            repositories,
                            household_id=household_id,
                            item_view=item_view,
                            generation_instruction=None,
                        )
                        generated_count += 1

            await session.commit()
            return generated_count

    async def _generate_and_persist_recipe(
        self,
        repositories: PlanningRepositories,
        *,
        household_id: UUID,
        item_view: StoredPlanItemView,
        generation_instruction: str | None,
    ) -> StoredPlanItemView:
        generation_context = await repositories.weekly_plan_repository.get_generation_context(
            item_view.weekly_plan_id,
        )
        if generation_context is None:
            raise ValueError("Не удалось восстановить контекст блюда.")

        reference_recipes = await _collect_reference_recipes(
            self._recipe_hint_provider,
            generation_context,
            item_view.name,
        )

        if generation_instruction is None:
            recipe_details = await self._recipe_client.expand_item_recipe(
                item_view=item_view,
                generation_context=generation_context,
                reference_recipes=reference_recipes,
            )
        else:
            recipe_details = await self._recipe_client.adjust_item_recipe(
                item_view=item_view,
                generation_context=generation_context,
                instruction=generation_instruction,
                reference_recipes=reference_recipes,
            )

        updated_payload = dict(item_view.snapshot_payload)
        updated_payload.update(_serialize_recipe_details(recipe_details))
        updated_payload["recipe_generation_source"] = (
            "ai_recipe_feedback" if generation_instruction is not None else "ai_recipe_expansion"
        )
        if generation_instruction is not None:
            updated_payload["recipe_feedback_note"] = generation_instruction

        await repositories.weekly_plan_repository.update_item_snapshot(
            PlannedMealItemReplacement(
                planned_meal_item_id=item_view.planned_meal_item_id,
                name=item_view.name,
                summary=recipe_details.summary or item_view.summary or "Без краткого описания",
                adaptation_notes=item_view.adaptation_notes,
                snapshot_payload=updated_payload,
                clear_dish_link=False,
            ),
        )

        updated_item = await repositories.weekly_plan_repository.get_item_view(
            household_id,
            item_view.planned_meal_item_id,
        )
        if updated_item is None:
            raise ValueError("Не удалось прочитать обновленный рецепт.")
        return updated_item


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


async def _resolve_latest_visible_plan(
    repositories: PlanningRepositories,
    household_id: UUID,
) -> StoredDraftPlan | StoredPlanReference | None:
    latest_draft = await repositories.weekly_plan_repository.get_latest_draft_for_household(
        household_id,
    )
    if latest_draft is not None:
        return latest_draft
    return await repositories.weekly_plan_repository.get_latest_confirmed_for_household(
        household_id,
    )


def _has_recipe_details(item_view: StoredPlanItemView) -> bool:
    payload = item_view.snapshot_payload
    if isinstance(payload.get("ingredients"), list) and payload["ingredients"]:
        return True
    for field_name in ("preparation_steps", "cooking_steps", "serving_steps"):
        if isinstance(payload.get(field_name), list) and payload[field_name]:
            return True
    return False


def _serialize_recipe_details(recipe_details: RecipeDetails) -> dict[str, object]:
    payload: dict[str, object] = {}
    if recipe_details.summary is not None:
        payload["summary"] = recipe_details.summary
    payload["ingredients"] = [
        {
            "name": ingredient.name,
            "amount": ingredient.amount,
            "preparation_note": ingredient.preparation_note,
        }
        for ingredient in recipe_details.ingredients
    ]
    payload["preparation_steps"] = recipe_details.preparation_steps
    payload["cooking_steps"] = recipe_details.cooking_steps
    payload["serving_steps"] = recipe_details.serving_steps
    payload["prep_time_minutes"] = recipe_details.prep_time_minutes
    payload["cook_time_minutes"] = recipe_details.cook_time_minutes
    payload["serving_notes"] = recipe_details.serving_notes
    payload["recipe_generated"] = True
    return payload


async def _collect_reference_recipes(
    recipe_hint_provider: RecipeHintProvider | None,
    generation_context: WeeklyPlanGenerationContext,
    dish_name: str,
) -> list[RecipeHint]:
    if recipe_hint_provider is None:
        return []
    return await recipe_hint_provider.search_related_recipes(dish_name, generation_context)
