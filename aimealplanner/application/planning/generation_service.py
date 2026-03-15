from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedWeekPlan,
    WeeklyPlanGenerationClient,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.repositories import PlanningRepositoryBundleFactory


@dataclass(frozen=True, slots=True)
class GeneratedWeekPlanResult:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    rendered_message: str


class WeeklyPlanGenerationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        generation_client: WeeklyPlanGenerationClient,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._generation_client = generation_client

    async def generate_for_plan(self, weekly_plan_id: UUID) -> GeneratedWeekPlanResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            context = await repositories.weekly_plan_repository.get_generation_context(
                weekly_plan_id,
            )
            if context is None:
                raise ValueError("Черновик плана не найден.")

            generated_plan = await self._generation_client.generate_week_plan(context)
            await repositories.weekly_plan_repository.replace_generated_meals(
                context.weekly_plan_id,
                generated_plan,
            )
            await session.commit()
            return GeneratedWeekPlanResult(
                weekly_plan_id=context.weekly_plan_id,
                start_date=context.start_date,
                end_date=context.end_date,
                rendered_message=render_generated_week_plan(context, generated_plan),
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
        lines.append(meal_date.strftime("%d.%m.%Y"))
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
