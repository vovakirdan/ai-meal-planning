# ruff: noqa: RUF001
from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import pytest
from aimealplanner.application.planning.generation_dto import (
    DishQuickAction,
    WeeklyPlanGenerationContext,
)
from aimealplanner.infrastructure.ai.openai_client import (
    _parse_adjustment_payload,
    _parse_feedback_comment_payload,
    _parse_recipe_details_payload,
    _parse_replacement_payload,
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
                            "suggested_actions": [
                                {"label": "Легче", "instruction": "Сделай блюдо легче."},
                                {
                                    "label": "Мягче вкус",
                                    "instruction": "Сделай вкус мягче.",
                                },
                            ],
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
                            "suggested_actions": [
                                {"label": "Сытнее", "instruction": "Сделай завтрак сытнее."},
                                {
                                    "label": "Легче",
                                    "instruction": "Сделай блюдо легче.",
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    )

    parsed = _parse_week_plan_payload(context, raw_content)

    assert [meal.slot for meal in parsed.meals] == ["breakfast", "dinner"]
    assert parsed.meals[0].items[0].adaptation_notes == ["less sugar"]
    assert parsed.meals[0].items[0].suggested_actions == [
        DishQuickAction(label="Сытнее", instruction="Сделай завтрак сытнее."),
        DishQuickAction(label="Легче", instruction="Сделай блюдо легче."),
    ]


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
                            "suggested_actions": [
                                {"label": "Сытнее", "instruction": "Сделай завтрак сытнее."},
                                {
                                    "label": "Легче",
                                    "instruction": "Сделай блюдо легче.",
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="AI payload is missing meals"):
        _parse_week_plan_payload(context, raw_content)


def test_parse_replacement_payload_accepts_exactly_three_unique_candidates() -> None:
    raw_content = json.dumps(
        {
            "candidates": [
                {
                    "name": "Рыба с рисом",
                    "summary": "Легкий ужин без тяжести",
                    "adaptation_notes": ["без оливок"],
                    "suggested_actions": [
                        {"label": "Легче", "instruction": "Сделай блюдо легче."},
                        {
                            "label": "Мягче вкус",
                            "instruction": "Сделай вкус мягче.",
                        },
                    ],
                    "reason": "Подходит под ограничения семьи",
                },
                {
                    "name": "Курица с булгуром",
                    "summary": "Быстрый ужин на будни",
                    "adaptation_notes": [],
                    "suggested_actions": [
                        {"label": "Легче", "instruction": "Сделай блюдо легче."},
                        {
                            "label": "Мягче вкус",
                            "instruction": "Сделай вкус мягче.",
                        },
                    ],
                    "reason": None,
                },
                {
                    "name": "Тефтели с картофелем",
                    "summary": "Более привычный семейный вариант",
                    "adaptation_notes": ["меньше масла"],
                    "suggested_actions": [
                        {"label": "Легче", "instruction": "Сделай блюдо легче."},
                        {
                            "label": "Мягче вкус",
                            "instruction": "Сделай вкус мягче.",
                        },
                    ],
                    "reason": "Сохраняет формат сытного ужина",
                },
            ],
        },
    )

    parsed = _parse_replacement_payload(raw_content, slot="dinner")

    assert [candidate.name for candidate in parsed] == [
        "Рыба с рисом",
        "Курица с булгуром",
        "Тефтели с картофелем",
    ]
    assert parsed[0].adaptation_notes == ["без оливок"]
    assert parsed[0].suggested_actions == [
        DishQuickAction(label="Легче", instruction="Сделай блюдо легче."),
        DishQuickAction(label="Мягче вкус", instruction="Сделай вкус мягче."),
    ]


def test_parse_replacement_payload_rejects_duplicate_names() -> None:
    raw_content = json.dumps(
        {
            "candidates": [
                {
                    "name": "Рыба с рисом",
                    "summary": "Легкий ужин",
                    "adaptation_notes": [],
                    "suggested_actions": [],
                    "reason": None,
                },
                {
                    "name": "Рыба с рисом",
                    "summary": "Почти то же самое",
                    "adaptation_notes": [],
                    "suggested_actions": [],
                    "reason": None,
                },
                {
                    "name": "Курица с булгуром",
                    "summary": "Быстрый ужин",
                    "adaptation_notes": [],
                    "suggested_actions": [],
                    "reason": None,
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="Duplicate replacement candidate"):
        _parse_replacement_payload(raw_content, slot="dinner")


def test_parse_adjustment_payload_accepts_single_adjusted_dish() -> None:
    raw_content = json.dumps(
        {
            "name": "Паста с курицей",
            "summary": "Менее острая и более мягкая версия ужина",
            "adaptation_notes": ["меньше острого перца"],
            "suggested_actions": [
                {"label": "Легче", "instruction": "Сделай блюдо легче."},
                {
                    "label": "Мягче вкус",
                    "instruction": "Сделай вкус мягче.",
                },
            ],
            "reason": "Убрана лишняя острота",
        },
    )

    parsed = _parse_adjustment_payload(raw_content, slot="dinner")

    assert parsed.name == "Паста с курицей"
    assert parsed.adaptation_notes == ["меньше острого перца"]
    assert parsed.suggested_actions == [
        DishQuickAction(label="Легче", instruction="Сделай блюдо легче."),
        DishQuickAction(label="Мягче вкус", instruction="Сделай вкус мягче."),
    ]


def test_parse_feedback_comment_payload_extracts_only_non_empty_fields() -> None:
    raw_content = json.dumps(
        {
            "planning_note": "Сделать блюдо менее жирным.",
            "restriction_candidate": "избегать слишком жирных сливочных блюд",
        },
    )

    parsed = _parse_feedback_comment_payload(raw_content)

    assert parsed == {
        "planning_note": "Сделать блюдо менее жирным.",
        "restriction_candidate": "избегать слишком жирных сливочных блюд",
    }


def test_parse_feedback_comment_payload_allows_empty_result() -> None:
    raw_content = json.dumps(
        {
            "planning_note": "   ",
            "restriction_candidate": None,
        },
    )

    parsed = _parse_feedback_comment_payload(raw_content)

    assert parsed == {}


def test_parse_recipe_details_payload_accepts_complete_recipe_details() -> None:
    raw_content = json.dumps(
        {
            "summary": "Мягкая домашняя версия блюда",
            "ingredients": [
                {
                    "name": "Тофу",
                    "amount": "300 г",
                    "preparation_note": "нарезать кубиками",
                },
                {
                    "name": "Рисовая лапша",
                    "amount": "200 г",
                    "preparation_note": None,
                },
                {
                    "name": "тофу",
                    "amount": "300 г",
                    "preparation_note": "дубликат",
                },
            ],
            "preparation_steps": [" Подготовить овощи. "],
            "cooking_steps": [" Быстро обжарить ингредиенты. "],
            "serving_steps": [" Подать сразу. "],
            "prep_time_minutes": 15,
            "cook_time_minutes": 12,
            "serving_notes": " Добавить кунжут перед подачей. ",
        },
    )

    parsed = _parse_recipe_details_payload(raw_content)

    assert parsed.summary == "Мягкая домашняя версия блюда"
    assert [ingredient.name for ingredient in parsed.ingredients] == [
        "Тофу",
        "Рисовая лапша",
    ]
    assert parsed.ingredients[0].amount == "300 г"
    assert parsed.ingredients[0].preparation_note == "нарезать кубиками"
    assert parsed.preparation_steps == ["Подготовить овощи."]
    assert parsed.cooking_steps == ["Быстро обжарить ингредиенты."]
    assert parsed.serving_steps == ["Подать сразу."]
    assert parsed.prep_time_minutes == 15
    assert parsed.cook_time_minutes == 12
    assert parsed.serving_notes == "Добавить кунжут перед подачей."


def test_parse_recipe_details_payload_rejects_missing_ingredients() -> None:
    raw_content = json.dumps(
        {
            "summary": "Пустой рецепт",
            "ingredients": [],
            "preparation_steps": [],
            "cooking_steps": [],
            "serving_steps": [],
            "prep_time_minutes": None,
            "cook_time_minutes": None,
            "serving_notes": None,
        },
    )

    with pytest.raises(ValueError, match="must include at least one ingredient"):
        _parse_recipe_details_payload(raw_content)
