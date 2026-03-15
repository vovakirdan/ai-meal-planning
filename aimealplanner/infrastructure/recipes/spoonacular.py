from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from aimealplanner.application.planning.generation_dto import (
    PlanningMemberContext,
    RecipeHint,
    RecipeHintIngredient,
    WeeklyPlanGenerationContext,
)
from aimealplanner.core.config import Settings

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_NON_WORD_RE = re.compile(r"^[^\w]+|[^\w]+$")
_MOOD_TO_CUISINE = {
    "Азиатская": "Asian",
    "Мексиканская": "Mexican",
    "Русская": "Eastern European",
    "Средиземноморская": "Mediterranean",
}
_MOOD_TO_DIET = {
    "Веганская": "vegan",
    "Вегетарианская": "vegetarian",
    "Постное меню": "vegan",
}
_FAVORITE_CUISINE_MAP = {
    "азиатская": "Asian",
    "мексиканская": "Mexican",
    "русская": "Eastern European",
    "средиземноморская": "Mediterranean",
    "итальянская": "Italian",
    "индийская": "Indian",
    "японская": "Japanese",
    "китайская": "Chinese",
    "тайская": "Thai",
}


@dataclass(slots=True)
class SpoonacularRecipeHintProvider:
    _client: httpx.AsyncClient
    _api_key: str
    _max_results: int = 3

    @classmethod
    def from_settings(cls, settings: Settings) -> SpoonacularRecipeHintProvider | None:
        if not settings.spoonacular_api_key:
            return None
        return cls(
            _client=httpx.AsyncClient(
                base_url=settings.spoonacular_base_url,
                timeout=httpx.Timeout(15.0, connect=5.0),
            ),
            _api_key=settings.spoonacular_api_key,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def collect_hints(
        self,
        context: WeeklyPlanGenerationContext,
    ) -> list[RecipeHint]:
        params = _build_search_params(context, max_results=self._max_results)
        if params is None:
            return []

        return await self._search(params)

    async def search_related_recipes(
        self,
        query: str,
        context: WeeklyPlanGenerationContext,
    ) -> list[RecipeHint]:
        params = _build_search_params(context, max_results=self._max_results, query=query)
        if params is None:
            return []
        return await self._search(params)

    async def _search(self, params: dict[str, str]) -> list[RecipeHint]:
        try:
            response = await self._client.get(
                "/recipes/complexSearch",
                params={"apiKey": self._api_key, **params},
            )
            response.raise_for_status()
        except httpx.HTTPError as err:
            logger.warning("spoonacular recipe hint lookup failed: %s", err)
            return []

        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            return []

        hints: list[RecipeHint] = []
        for recipe_payload in results:
            hint = _parse_recipe_hint(recipe_payload)
            if hint is not None:
                hints.append(hint)
        return hints

    async def lookup_recipe_by_id(self, recipe_id: int) -> RecipeHint | None:
        try:
            response = await self._client.get(
                f"/recipes/{recipe_id}/information",
                params={
                    "apiKey": self._api_key,
                    "includeNutrition": "false",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as err:
            logger.warning("spoonacular recipe lookup failed for recipe_id=%s: %s", recipe_id, err)
            return None

        return _parse_recipe_hint(response.json())


def _build_search_params(
    context: WeeklyPlanGenerationContext,
    *,
    max_results: int,
    query: str | None = None,
) -> dict[str, str] | None:
    cuisines = _collect_cuisine_hints(context)
    diet = _map_diet_hint(context.week_mood)
    excluded_ingredients = _collect_excluded_ingredients(context.members)

    if not cuisines and diet is None and not excluded_ingredients and query is None:
        return None

    params: dict[str, str] = {
        "number": str(max_results),
        "addRecipeInformation": "true",
        "fillIngredients": "true",
        "instructionsRequired": "true",
        "sort": "popularity",
        "type": "main course",
    }
    if query is not None and query.strip():
        params["query"] = query.strip()
    if cuisines:
        params["cuisine"] = ",".join(cuisines)
    if diet is not None:
        params["diet"] = diet
    if excluded_ingredients:
        params["excludeIngredients"] = ",".join(excluded_ingredients)
    return params


def _collect_cuisine_hints(context: WeeklyPlanGenerationContext) -> list[str]:
    hints: list[str] = []
    if context.week_mood in _MOOD_TO_CUISINE:
        hints.append(_MOOD_TO_CUISINE[context.week_mood])

    for member in context.members:
        for favorite_cuisine in member.favorite_cuisines:
            mapped_cuisine = _map_favorite_cuisine(favorite_cuisine)
            if mapped_cuisine is not None:
                hints.append(mapped_cuisine)

    seen: set[str] = set()
    deduped_hints: list[str] = []
    for hint in hints:
        if hint in seen:
            continue
        seen.add(hint)
        deduped_hints.append(hint)
    return deduped_hints[:3]


def _map_favorite_cuisine(value: str) -> str | None:
    normalized_value = value.strip().lower()
    if not normalized_value:
        return None
    return _FAVORITE_CUISINE_MAP.get(normalized_value)


def _map_diet_hint(week_mood: str | None) -> str | None:
    if week_mood is None:
        return None
    return _MOOD_TO_DIET.get(week_mood)


def _collect_excluded_ingredients(members: list[PlanningMemberContext]) -> list[str]:
    raw_constraints: list[str] = []
    for member in members:
        raw_constraints.extend(member.constraints)

    normalized_constraints: list[str] = []
    for raw_constraint in raw_constraints:
        normalized_constraint = _normalize_constraint(raw_constraint)
        if normalized_constraint:
            normalized_constraints.append(normalized_constraint)

    seen: set[str] = set()
    deduped_constraints: list[str] = []
    for constraint in normalized_constraints:
        if constraint in seen:
            continue
        seen.add(constraint)
        deduped_constraints.append(constraint)
    return deduped_constraints[:10]


def _normalize_constraint(value: str) -> str | None:
    normalized_value = value.strip().lower()
    if not normalized_value:
        return None

    for prefix in ("без ", "no ", "not ", "не "):
        if normalized_value.startswith(prefix):
            normalized_value = normalized_value[len(prefix) :]
            break

    normalized_value = _NON_WORD_RE.sub("", normalized_value)
    return normalized_value or None


def _parse_recipe_hint(payload: dict[str, Any]) -> RecipeHint | None:
    recipe_id = payload.get("id")
    title = payload.get("title")
    if recipe_id is None or not isinstance(title, str) or not title.strip():
        return None

    cuisines = payload.get("cuisines")
    diets = payload.get("diets")
    extended_ingredients = payload.get("extendedIngredients")
    summary = payload.get("summary")

    return RecipeHint(
        provider="spoonacular",
        external_id=str(recipe_id),
        title=title.strip(),
        source_url=_coerce_optional_str(payload.get("sourceUrl")),
        cuisines=[str(value).strip() for value in cuisines if str(value).strip()]
        if isinstance(cuisines, list)
        else [],
        diets=[str(value).strip() for value in diets if str(value).strip()]
        if isinstance(diets, list)
        else [],
        summary=_strip_html(_coerce_optional_str(summary)),
        ready_in_minutes=_coerce_optional_int(payload.get("readyInMinutes")),
        servings=_coerce_optional_int(payload.get("servings")),
        ingredients=_parse_ingredients(extended_ingredients),
    )


def _parse_ingredients(payload: Any) -> list[RecipeHintIngredient]:
    if not isinstance(payload, list):
        return []

    ingredients: list[RecipeHintIngredient] = []
    for item in payload[:8]:
        if not isinstance(item, dict):
            continue
        name = _coerce_optional_str(item.get("originalName")) or _coerce_optional_str(
            item.get("name"),
        )
        if name is None:
            continue
        amount = _coerce_optional_str(item.get("original")) or _coerce_optional_str(
            item.get("originalString"),
        )
        ingredients.append(
            RecipeHintIngredient(
                name=name,
                amount=amount,
            ),
        )
    return ingredients


def _coerce_optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized_value = value.strip()
    return normalized_value or None


def _strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    return _HTML_TAG_RE.sub("", value).strip() or None
