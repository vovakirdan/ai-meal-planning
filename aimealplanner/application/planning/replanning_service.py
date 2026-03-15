# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDayView,
    StoredPlanMealView,
)
from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedWeekPlan,
    RecipeHintProvider,
    WeeklyPlanGenerationClient,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)


@dataclass(frozen=True, slots=True)
class ReplannedMealResult:
    updated_meal: StoredPlanMealView


@dataclass(frozen=True, slots=True)
class ReplannedDayResult:
    updated_day: StoredPlanDayView


class PlanReplanningService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        generation_client: WeeklyPlanGenerationClient,
        recipe_hint_provider: RecipeHintProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._generation_client = generation_client
        self._recipe_hint_provider = recipe_hint_provider

    async def replan_meal(
        self,
        telegram_user_id: int,
        planned_meal_id: UUID,
    ) -> ReplannedMealResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            meal_view = await repositories.weekly_plan_repository.get_meal_view(
                household_id,
                planned_meal_id,
            )
            if meal_view is None:
                raise ValueError("Не удалось открыть выбранный прием пищи.")

            day_view = await repositories.weekly_plan_repository.get_day_view(
                household_id,
                meal_view.weekly_plan_id,
                meal_view.meal_date,
            )
            if day_view is None:
                raise ValueError("Не удалось открыть день для пересборки.")

            context = await repositories.weekly_plan_repository.get_generation_context(
                meal_view.weekly_plan_id,
            )
            if context is None:
                raise ValueError("Не удалось восстановить контекст недели.")

            replanning_context = _build_meal_replanning_context(
                context,
                meal_view=meal_view,
                day_view=day_view,
            )
            generated_plan = await self._generate_scoped_plan(replanning_context)
            generated_meal = _validate_meal_replanning_result(
                generated_plan,
                meal_view=meal_view,
            )

            await repositories.weekly_plan_repository.replace_meal_with_generated(
                household_id,
                planned_meal_id,
                generated_meal,
            )
            await session.commit()

            updated_meal = await repositories.weekly_plan_repository.get_meal_view(
                household_id,
                planned_meal_id,
            )
            if updated_meal is None:
                raise ValueError("Не удалось прочитать обновленный прием пищи.")
            return ReplannedMealResult(updated_meal=updated_meal)

    async def replan_day(
        self,
        telegram_user_id: int,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> ReplannedDayResult:
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

            context = await repositories.weekly_plan_repository.get_generation_context(
                weekly_plan_id
            )
            if context is None:
                raise ValueError("Не удалось восстановить контекст недели.")

            replanning_context = _build_day_replanning_context(
                context,
                day_view=day_view,
            )
            generated_plan = await self._generate_scoped_plan(replanning_context)
            _validate_day_replanning_result(
                generated_plan,
                meal_date=meal_date,
                expected_slots=context.active_slots,
            )
            await repositories.weekly_plan_repository.replace_day_with_generated(
                household_id,
                weekly_plan_id,
                meal_date,
                generated_plan,
            )
            await session.commit()

            updated_day = await repositories.weekly_plan_repository.get_day_view(
                household_id,
                weekly_plan_id,
                meal_date,
            )
            if updated_day is None:
                raise ValueError("Не удалось прочитать обновленный день.")
            return ReplannedDayResult(updated_day=updated_day)

    async def _generate_scoped_plan(
        self,
        context: WeeklyPlanGenerationContext,
    ) -> GeneratedWeekPlan:
        enriched_context = context
        if self._recipe_hint_provider is not None:
            reference_recipes = await self._recipe_hint_provider.collect_hints(context)
            enriched_context = replace(context, reference_recipes=reference_recipes)
        return await self._generation_client.generate_week_plan(enriched_context)


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


def _build_meal_replanning_context(
    context: WeeklyPlanGenerationContext,
    *,
    meal_view: StoredPlanMealView,
    day_view: StoredPlanDayView,
) -> WeeklyPlanGenerationContext:
    updated_payload = dict(context.context_payload)
    updated_payload.update(
        {
            "replanning_scope": "meal",
            "replanning_target_date": meal_view.meal_date.isoformat(),
            "replanning_target_slot": meal_view.slot,
            "replanning_current_scope": _render_meal_snapshot(meal_view),
            "replanning_current_day": _render_day_snapshot(day_view),
        },
    )
    return replace(
        context,
        start_date=meal_view.meal_date,
        end_date=meal_view.meal_date,
        active_slots=[meal_view.slot],
        context_payload=updated_payload,
    )


def _build_day_replanning_context(
    context: WeeklyPlanGenerationContext,
    *,
    day_view: StoredPlanDayView,
) -> WeeklyPlanGenerationContext:
    updated_payload = dict(context.context_payload)
    updated_payload.update(
        {
            "replanning_scope": "day",
            "replanning_target_date": day_view.meal_date.isoformat(),
            "replanning_current_day": _render_day_snapshot(day_view),
        },
    )
    return replace(
        context,
        start_date=day_view.meal_date,
        end_date=day_view.meal_date,
        context_payload=updated_payload,
    )


def _validate_meal_replanning_result(
    generated_plan: GeneratedWeekPlan,
    *,
    meal_view: StoredPlanMealView,
) -> GeneratedMeal:
    if len(generated_plan.meals) != 1:
        raise ValueError("Не удалось корректно пересобрать выбранный прием пищи.")

    generated_meal = generated_plan.meals[0]
    if generated_meal.meal_date != meal_view.meal_date or generated_meal.slot != meal_view.slot:
        raise ValueError("AI вернул другой день или слот вместо выбранного приема пищи.")
    return generated_meal


def _validate_day_replanning_result(
    generated_plan: GeneratedWeekPlan,
    *,
    meal_date: date,
    expected_slots: list[str],
) -> None:
    if not generated_plan.meals:
        raise ValueError("Не удалось корректно пересобрать выбранный день.")

    if any(meal.meal_date != meal_date for meal in generated_plan.meals):
        raise ValueError("AI вернул блюда не для того дня, который нужно пересобрать.")

    generated_slots = [meal.slot for meal in generated_plan.meals]
    if len(set(generated_slots)) != len(generated_slots):
        raise ValueError("AI вернул дублирующиеся приемы пищи для выбранного дня.")

    if set(generated_slots) != set(expected_slots):
        raise ValueError("AI вернул неполный или несовместимый набор приемов пищи для дня.")


def _render_day_snapshot(day_view: StoredPlanDayView) -> str:
    if not day_view.meals:
        return "День пока пуст."
    return "\n".join(
        [
            (
                f"- {_render_slot_label(meal.slot)}: "
                f"{', '.join(meal.item_names) if meal.item_names else 'пока без блюд'}"
            )
            for meal in day_view.meals
        ],
    )


def _render_meal_snapshot(meal_view: StoredPlanMealView) -> str:
    item_names = (
        ", ".join(item.name for item in meal_view.items) if meal_view.items else "пока без блюд"
    )
    return f"{_render_slot_label(meal_view.slot)}: {item_names}"


def _render_slot_label(slot: str) -> str:
    slot_labels = {
        "breakfast": "Завтрак",
        "lunch": "Обед",
        "dinner": "Ужин",
        "snack_1": "Перекус 1",
        "snack_2": "Перекус 2",
        "dessert": "Десерт",
    }
    return slot_labels.get(slot, slot)
