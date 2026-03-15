from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedWeekPlan,
    RecipeHintProvider,
    WeeklyPlanGenerationClient,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.repositories import PlanningRepositoryBundleFactory


@dataclass(frozen=True, slots=True)
class GeneratedWeekPlanResult:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    meals_count: int
    items_count: int
    rendered_message: str


class WeeklyPlanGenerationService:
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

    async def generate_for_plan(self, weekly_plan_id: UUID) -> GeneratedWeekPlanResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            context = await repositories.weekly_plan_repository.get_generation_context(
                weekly_plan_id,
            )
            if context is None:
                raise ValueError("Черновик плана не найден.")

            enriched_context = context
            if self._recipe_hint_provider is not None:
                reference_recipes = await self._recipe_hint_provider.collect_hints(context)
                enriched_context = replace(context, reference_recipes=reference_recipes)

            generated_plan = await self._generation_client.generate_week_plan(enriched_context)
            await repositories.weekly_plan_repository.replace_generated_meals(
                enriched_context.weekly_plan_id,
                generated_plan,
            )
            await session.commit()
            return GeneratedWeekPlanResult(
                weekly_plan_id=enriched_context.weekly_plan_id,
                start_date=enriched_context.start_date,
                end_date=enriched_context.end_date,
                meals_count=len(generated_plan.meals),
                items_count=sum(len(meal.items) for meal in generated_plan.meals),
                rendered_message=render_generated_week_plan(enriched_context, generated_plan),
            )


def render_generated_week_plan(
    context: WeeklyPlanGenerationContext,
    generated_plan: GeneratedWeekPlan,
) -> str:
    header = (
        "План недели готов.\n"
        f"Период: {context.start_date.strftime('%d.%m.%Y')} - "
        f"{context.end_date.strftime('%d.%m.%Y')}."
    )
    meals_by_day: dict[date, list[GeneratedMeal]] = {}
    for meal in generated_plan.meals:
        meals_by_day.setdefault(meal.meal_date, []).append(meal)

    lines = [header]
    for meal_date in sorted(meals_by_day):
        lines.append("")
        lines.append(f"{meal_date.strftime('%d.%m.%Y')} ({_weekday_name(meal_date)})")
        for meal in meals_by_day[meal_date]:
            item_names = ", ".join(item.name for item in meal.items)
            lines.append(f"{_render_slot_name(meal.slot)}: {item_names}")
    return "\n".join(lines)


def _render_slot_name(slot: str) -> str:
    slot_labels = {
        "breakfast": "Завтрак",
        "lunch": "Обед",
        "dinner": "Ужин",
        "snack_1": "Перекус 1",
        "snack_2": "Перекус 2",
        "dessert": "Десерт",
    }
    if slot not in slot_labels:
        raise ValueError(f"Unknown meal slot: {slot}")
    return slot_labels[slot]


def _weekday_name(value: date) -> str:
    weekdays = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return weekdays[value.weekday()]
