from __future__ import annotations

import httpx
import pytest
from aimealplanner.application.planning.generation_dto import (
    PlanningMemberContext,
    WeeklyPlanGenerationContext,
)
from aimealplanner.infrastructure.db.enums import RepeatabilityMode
from aimealplanner.infrastructure.recipes.spoonacular import (
    SpoonacularRecipeHintProvider,
)


def _build_generation_context() -> WeeklyPlanGenerationContext:
    from datetime import date
    from uuid import uuid4

    return WeeklyPlanGenerationContext(
        weekly_plan_id=uuid4(),
        household_id=uuid4(),
        timezone="Europe/Moscow",
        start_date=date(2026, 3, 23),
        end_date=date(2026, 3, 29),
        meal_count_per_day=3,
        desserts_enabled=False,
        repeatability_mode=RepeatabilityMode.BALANCED,
        active_slots=["breakfast", "lunch", "dinner"],
        week_mood="Средиземноморская",
        weekly_notes=None,
        pantry_considered=False,
        context_payload={"source": "test"},
        members=[
            PlanningMemberContext(
                display_name="Вова",
                constraints=["без оливок"],
                favorite_cuisines=["Средиземноморская"],
                profile_note=None,
            ),
        ],
        pantry_items=[],
    )


@pytest.mark.asyncio
async def test_collect_hints_maps_spoonacular_payload_to_recipe_hints() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/recipes/complexSearch"
        assert request.url.params["cuisine"] == "Mediterranean"
        assert request.url.params["excludeIngredients"] == "оливок"
        assert request.url.params["type"] == "main course"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 101,
                        "title": "Mediterranean Chicken",
                        "sourceUrl": "https://example.test/recipe",
                        "cuisines": ["Mediterranean"],
                        "diets": ["gluten free"],
                        "summary": "<b>Bright</b> and fresh dinner",
                        "readyInMinutes": 35,
                        "servings": 4,
                        "extendedIngredients": [
                            {
                                "originalName": "chicken breast",
                                "original": "2 chicken breasts",
                            },
                            {
                                "originalName": "tomatoes",
                                "original": "3 tomatoes",
                            },
                        ],
                    },
                ],
            },
        )

    provider = SpoonacularRecipeHintProvider(
        _client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://api.spoonacular.com",
        ),
        _api_key="test-key",
    )

    try:
        hints = await provider.collect_hints(_build_generation_context())
    finally:
        await provider.close()

    assert len(hints) == 1
    assert hints[0].title == "Mediterranean Chicken"
    assert hints[0].provider == "spoonacular"
    assert hints[0].summary == "Bright and fresh dinner"
    assert [ingredient.name for ingredient in hints[0].ingredients] == [
        "chicken breast",
        "tomatoes",
    ]


@pytest.mark.asyncio
async def test_collect_hints_returns_empty_list_when_no_filters_are_available() -> None:
    from dataclasses import replace

    provider = SpoonacularRecipeHintProvider(
        _client=httpx.AsyncClient(base_url="https://api.spoonacular.com"),
        _api_key="test-key",
    )
    context = replace(
        _build_generation_context(),
        week_mood=None,
        members=[
            PlanningMemberContext(
                display_name="Вова",
                constraints=[],
                favorite_cuisines=[],
                profile_note=None,
            ),
        ],
    )

    try:
        hints = await provider.collect_hints(context)
    finally:
        await provider.close()

    assert hints == []
