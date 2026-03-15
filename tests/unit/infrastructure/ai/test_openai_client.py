from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import pytest
from aimealplanner.application.planning.generation_dto import (
    WeeklyPlanGenerationContext,
)
from aimealplanner.infrastructure.ai.openai_client import (
    _parse_week_plan_payload,
)
from aimealplanner.infrastructure.db.enums import RepeatabilityMode


def _build_generation_context() -> WeeklyPlanGenerationContext:
    return WeeklyPlanGenerationContext(
        weekly_plan_id=uuid4(),
        household_id=uuid4(),
        timezone="Europe/Moscow",
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 23),
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


def test_parse_week_plan_payload_accepts_complete_plan_and_sorts_meals() -> None:
    context = _build_generation_context()
    raw_content = json.dumps(
        {
            "meals": [
                {
                    "date": "2026-03-23",
                    "slot": "dinner",
                    "note": None,
                    "items": [
                        {
                            "name": "Pasta",
                            "summary": "Dinner pasta",
                            "adaptation_notes": [],
                        },
                    ],
                },
                {
                    "date": "2026-03-23",
                    "slot": "breakfast",
                    "note": None,
                    "items": [
                        {
                            "name": "Oatmeal",
                            "summary": "Warm breakfast",
                            "adaptation_notes": ["less sugar"],
                        },
                    ],
                },
            ],
        },
    )

    parsed = _parse_week_plan_payload(context, raw_content)

    assert [meal.slot for meal in parsed.meals] == ["breakfast", "dinner"]
    assert parsed.meals[0].items[0].adaptation_notes == ["less sugar"]


def test_parse_week_plan_payload_rejects_missing_expected_meal() -> None:
    context = _build_generation_context()
    raw_content = json.dumps(
        {
            "meals": [
                {
                    "date": "2026-03-23",
                    "slot": "breakfast",
                    "note": None,
                    "items": [
                        {
                            "name": "Oatmeal",
                            "summary": "Warm breakfast",
                            "adaptation_notes": [],
                        },
                    ],
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="AI payload is missing meals"):
        _parse_week_plan_payload(context, raw_content)
