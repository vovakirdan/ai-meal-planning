from __future__ import annotations

from datetime import date
from uuid import uuid4

from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedMealItem,
    GeneratedWeekPlan,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.generation_service import (
    render_generated_week_plan,
)
from aimealplanner.infrastructure.db.enums import RepeatabilityMode


def _build_generation_context() -> WeeklyPlanGenerationContext:
    return WeeklyPlanGenerationContext(
        weekly_plan_id=uuid4(),
        household_id=uuid4(),
        timezone="Europe/Moscow",
        start_date=date(2026, 3, 31),
        end_date=date(2026, 4, 1),
        meal_count_per_day=2,
        desserts_enabled=False,
        repeatability_mode=RepeatabilityMode.BALANCED,
        active_slots=["breakfast", "dinner"],
        week_mood=None,
        weekly_notes=None,
        pantry_considered=False,
        context_payload={"source": "test"},
        members=[],
        pantry_items=[],
    )


def test_render_generated_week_plan_orders_days_chronologically() -> None:
    context = _build_generation_context()
    generated_plan = GeneratedWeekPlan(
        meals=[
            GeneratedMeal(
                meal_date=date(2026, 4, 1),
                slot="dinner",
                note=None,
                items=[
                    GeneratedMealItem(
                        name="Pasta",
                        summary="Short summary",
                        adaptation_notes=[],
                    ),
                ],
            ),
            GeneratedMeal(
                meal_date=date(2026, 3, 31),
                slot="breakfast",
                note=None,
                items=[
                    GeneratedMealItem(
                        name="Oatmeal",
                        summary="Short summary",
                        adaptation_notes=[],
                    ),
                ],
            ),
        ],
    )

    rendered = render_generated_week_plan(context, generated_plan)

    assert rendered.index("31.03.2026") < rendered.index("01.04.2026")
