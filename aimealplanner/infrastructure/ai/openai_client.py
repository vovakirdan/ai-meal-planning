# ruff: noqa: RUF001
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.generation_dto import (
    GeneratedMeal,
    GeneratedMealItem,
    GeneratedWeekPlan,
    RecipeHint,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.replacement_dto import ReplacementCandidate
from aimealplanner.core.config import Settings

logger = logging.getLogger(__name__)


class _GeneratedMealItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    adaptation_notes: list[str] = Field(default_factory=list)


class _GeneratedMealModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    slot: str
    note: str | None = None
    items: list[_GeneratedMealItemModel]


class _GeneratedWeekPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meals: list[_GeneratedMealModel]


class _ReplacementCandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    adaptation_notes: list[str] = Field(default_factory=list)
    reason: str | None = None


class _ReplacementCandidatesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[_ReplacementCandidateModel]


@dataclass(slots=True)
class OpenAIWeeklyPlanGenerator:
    _client: AsyncOpenAI
    _model: str

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIWeeklyPlanGenerator:
        return cls(
            _client=AsyncOpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
            ),
            _model=settings.ai_model,
        )

    async def close(self) -> None:
        await self._client.close()

    async def generate_week_plan(
        self,
        context: WeeklyPlanGenerationContext,
    ) -> GeneratedWeekPlan:
        prompt = _build_week_plan_prompt(context)
        raw_content = await self._request_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
        try:
            return _parse_week_plan_payload(context, raw_content)
        except ValueError as err:
            logger.warning("weekly plan payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=_build_repair_prompt(context, raw_content, str(err)),
            )
            return _parse_week_plan_payload(context, repaired_content)

    async def suggest_replacements(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        reference_recipes: list[RecipeHint],
    ) -> list[ReplacementCandidate]:
        prompt = _build_replacement_prompt(
            item_view=item_view,
            generation_context=generation_context,
            reference_recipes=reference_recipes,
        )
        raw_content = await self._request_json(
            system_prompt=_REPLACEMENT_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
        try:
            return _parse_replacement_payload(raw_content)
        except ValueError as err:
            logger.warning("replacement payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_REPLACEMENT_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_replacement_payload(repaired_content)

    async def adjust_item(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        instruction: str,
        reference_recipes: list[RecipeHint],
    ) -> ReplacementCandidate:
        raw_content = await self._request_json(
            system_prompt=_ADJUSTMENT_SYSTEM_PROMPT,
            user_prompt=_build_adjustment_prompt(
                item_view=item_view,
                generation_context=generation_context,
                instruction=instruction,
                reference_recipes=reference_recipes,
            ),
        )
        try:
            return _parse_adjustment_payload(raw_content)
        except ValueError as err:
            logger.warning("adjustment payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_ADJUSTMENT_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_adjustment_payload(repaired_content)

    async def _request_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=5000,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("AI returned an empty response")
        return content


_SYSTEM_PROMPT = """
You are a meal planning assistant for a Telegram bot.
Return valid JSON only.
Do not use markdown fences.
Do not add commentary outside the JSON object.
Generate a realistic weekly household meal plan that respects constraints,
pantry hints, and week context.
Keep dish names and summaries in Russian.
""".strip()


_REPLACEMENT_SYSTEM_PROMPT = """
You help a Telegram meal planner bot replace one dish inside a weekly draft.
Return valid JSON only.
Do not use markdown fences.
Do not add commentary outside the JSON object.
Keep replacement names, summaries, and adaptation notes in Russian.
""".strip()


_ADJUSTMENT_SYSTEM_PROMPT = """
You help a Telegram meal planner bot adjust one dish inside a weekly draft.
Return valid JSON only.
Do not use markdown fences.
Do not add commentary outside the JSON object.
Keep the adjusted dish name, summary, and adaptation notes in Russian.
""".strip()


def _build_week_plan_prompt(context: WeeklyPlanGenerationContext) -> str:
    pantry_text = "ignore pantry" if not context.pantry_considered else _render_pantry(context)
    reference_recipes_text = _render_reference_recipes(context)
    member_lines = "\n".join(
        [
            (
                f"- {member.display_name}: ограничения={_render_list(member.constraints)}, "
                f"любит={_render_list(member.favorite_cuisines)}, "
                f"заметка={member.profile_note or 'нет'}"
            )
            for member in context.members
        ],
    )
    expected_slots = ", ".join(context.active_slots)
    expected_meals = "\n".join(
        [
            f"- {current_date.isoformat()}: {expected_slots}"
            for current_date in _iter_dates(context.start_date, context.end_date)
        ],
    )
    week_mood = context.week_mood or "без явного уклона"
    weekly_notes = context.weekly_notes or "нет отдельных пожеланий"
    return f"""
Build a weekly household meal plan.

Period:
- start_date: {context.start_date.isoformat()}
- end_date: {context.end_date.isoformat()}
- timezone: {context.timezone}

Week template:
- meal_count_per_day: {context.meal_count_per_day}
- desserts_enabled: {str(context.desserts_enabled).lower()}
- repeatability_mode: {context.repeatability_mode.value}
- active_slots: {expected_slots}

Week context:
- week_mood: {week_mood}
- weekly_notes: {weekly_notes}
- pantry: {pantry_text}

Household members:
{member_lines}

Recipe references:
{reference_recipes_text}

Requirements:
- Return meals for every date/slot pair listed below.
- Return 1-2 dish items for each meal.
- Never use explicitly forbidden ingredients.
- If pantry is enabled, prefer using what is already at home.
- You may use the recipe references as optional inspiration, but they are not the source of truth.
- It is acceptable to ignore the references if they do not fit the household context well.
- summary must be one short phrase.
- adaptation_notes must be an empty list if there are no adaptations.

Required JSON shape:
{{
  "meals": [
    {{
      "date": "YYYY-MM-DD",
      "slot": "breakfast|lunch|dinner|snack_1|snack_2|dessert",
      "note": "optional string or null",
      "items": [
        {{
          "name": "string",
          "summary": "string",
          "adaptation_notes": ["string"]
        }}
      ]
    }}
  ]
}}

Pairs to cover:
{expected_meals}
""".strip()


def _build_repair_prompt(
    context: WeeklyPlanGenerationContext,
    raw_content: str,
    error_message: str,
) -> str:
    return f"""
Исправь JSON так, чтобы он точно соответствовал требуемой схеме и покрывал все даты и слоты.
Верни только исправленный JSON.

Ошибка валидации:
{error_message}

Исходный JSON:
{raw_content}

Период: {context.start_date.isoformat()} - {context.end_date.isoformat()}
Слоты: {", ".join(context.active_slots)}
""".strip()


def _build_replacement_repair_prompt(raw_content: str, error_message: str) -> str:
    return f"""
Исправь JSON с вариантами замены блюда так, чтобы он точно соответствовал требуемой схеме.
Верни только исправленный JSON.

Ошибка валидации:
{error_message}

Исходный JSON:
{raw_content}
""".strip()


def _build_replacement_prompt(
    *,
    item_view: StoredPlanItemView,
    generation_context: WeeklyPlanGenerationContext,
    reference_recipes: list[RecipeHint],
) -> str:
    other_constraints = "\n".join(
        [
            (
                f"- {member.display_name}: ограничения={_render_list(member.constraints)}, "
                f"любит={_render_list(member.favorite_cuisines)}, "
                f"заметка={member.profile_note or 'нет'}"
            )
            for member in generation_context.members
        ],
    )
    references_text = _render_replacement_reference_recipes(reference_recipes)
    return f"""
Suggest 3 replacement dishes for one meal item inside a household weekly plan.

Current dish:
- name: {item_view.name}
- summary: {item_view.summary or "нет"}
- slot: {item_view.slot}
- meal_date: {item_view.meal_date.isoformat()}
- adaptation_notes: {_render_list(item_view.adaptation_notes)}

Week context:
- week_mood: {generation_context.week_mood or "без явного уклона"}
- weekly_notes: {generation_context.weekly_notes or "нет"}
- repeatability_mode: {generation_context.repeatability_mode.value}

Household:
{other_constraints}

Optional recipe references:
{references_text}

Requirements:
- Return exactly 3 candidates.
- Keep them suitable for the same meal slot.
- Avoid forbidden ingredients.
- Do not return the same dish with trivial wording changes.
- Prefer practical household dishes over restaurant-style outliers.
- reason should briefly explain why the replacement fits.
- adaptation_notes should be an empty list if there are no special adjustments.

Required JSON shape:
{{
  "candidates": [
    {{
      "name": "string",
      "summary": "string",
      "adaptation_notes": ["string"],
      "reason": "string or null"
    }}
  ]
}}
""".strip()


def _build_adjustment_prompt(
    *,
    item_view: StoredPlanItemView,
    generation_context: WeeklyPlanGenerationContext,
    instruction: str,
    reference_recipes: list[RecipeHint],
) -> str:
    references_text = _render_replacement_reference_recipes(reference_recipes)
    household_lines = "\n".join(
        [
            (
                f"- {member.display_name}: ограничения={_render_list(member.constraints)}, "
                f"любит={_render_list(member.favorite_cuisines)}, "
                f"заметка={member.profile_note or 'нет'}"
            )
            for member in generation_context.members
        ],
    )
    return f"""
Adjust one dish inside a household weekly plan.

Current dish:
- name: {item_view.name}
- summary: {item_view.summary or "нет"}
- slot: {item_view.slot}
- meal_date: {item_view.meal_date.isoformat()}
- adaptation_notes: {_render_list(item_view.adaptation_notes)}

Adjustment request:
- instruction: {instruction}

Week context:
- week_mood: {generation_context.week_mood or "без явного уклона"}
- weekly_notes: {generation_context.weekly_notes or "нет"}
- repeatability_mode: {generation_context.repeatability_mode.value}

Household:
{household_lines}

Optional recipe references:
{references_text}

Requirements:
- Keep the dish suitable for the same meal slot.
- Preserve the core idea of the dish unless the instruction clearly asks for a stronger change.
- Avoid forbidden ingredients.
- Prefer practical household cooking over restaurant-style complexity.
- reason should briefly explain what changed.
- adaptation_notes should be an empty list if there are no special adjustments.

Required JSON shape:
{{
  "name": "string",
  "summary": "string",
  "adaptation_notes": ["string"],
  "reason": "string or null"
}}
""".strip()


def _parse_week_plan_payload(
    context: WeeklyPlanGenerationContext,
    raw_content: str,
) -> GeneratedWeekPlan:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"AI returned invalid JSON: {err}") from err

    try:
        parsed = _GeneratedWeekPlanModel.model_validate(payload)
    except ValidationError as err:
        raise ValueError(f"AI payload failed schema validation: {err}") from err

    expected_pairs = {
        (current_date, slot)
        for current_date in _iter_dates(context.start_date, context.end_date)
        for slot in context.active_slots
    }
    generated_meals: list[GeneratedMeal] = []
    seen_pairs: set[tuple[date, str]] = set()
    for meal in parsed.meals:
        try:
            meal_date = date.fromisoformat(meal.date)
        except ValueError as err:
            raise ValueError(f"Invalid date in AI payload: {meal.date}") from err
        pair = (meal_date, meal.slot)
        if meal.slot not in context.active_slots:
            raise ValueError(f"Unexpected slot in AI payload: {meal.slot}")
        if pair in seen_pairs:
            raise ValueError(f"Duplicate meal in AI payload: {meal.date} {meal.slot}")
        if pair not in expected_pairs:
            raise ValueError(f"Meal outside expected range: {meal.date} {meal.slot}")
        if not meal.items:
            raise ValueError(f"Meal has no items: {meal.date} {meal.slot}")

        cleaned_items: list[GeneratedMealItem] = []
        for item in meal.items:
            name = item.name.strip()
            summary = item.summary.strip()
            if not name:
                raise ValueError(f"Meal item has empty name: {meal.date} {meal.slot}")
            if not summary:
                raise ValueError(f"Meal item has empty summary: {meal.date} {meal.slot}")

            cleaned_items.append(
                GeneratedMealItem(
                    name=name,
                    summary=summary,
                    adaptation_notes=[
                        note.strip() for note in item.adaptation_notes if note.strip()
                    ],
                ),
            )

        seen_pairs.add(pair)
        generated_meals.append(
            GeneratedMeal(
                meal_date=meal_date,
                slot=meal.slot,
                note=meal.note,
                items=cleaned_items,
            ),
        )

    missing_pairs = expected_pairs - seen_pairs
    if missing_pairs:
        missing_text = ", ".join(
            [f"{current_date.isoformat()} {slot}" for current_date, slot in sorted(missing_pairs)],
        )
        raise ValueError(f"AI payload is missing meals: {missing_text}")

    return GeneratedWeekPlan(
        meals=sorted(generated_meals, key=lambda meal: (meal.meal_date, meal.slot)),
    )


def _parse_replacement_payload(raw_content: str) -> list[ReplacementCandidate]:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"AI returned invalid JSON for replacements: {err}") from err

    try:
        parsed = _ReplacementCandidatesModel.model_validate(payload)
    except ValidationError as err:
        raise ValueError(f"AI replacement payload failed schema validation: {err}") from err

    candidates: list[ReplacementCandidate] = []
    seen_names: set[str] = set()
    for candidate in parsed.candidates:
        name = candidate.name.strip()
        summary = candidate.summary.strip()
        if not name:
            raise ValueError("Replacement candidate has empty name")
        if not summary:
            raise ValueError("Replacement candidate has empty summary")
        normalized_name = name.casefold()
        if normalized_name in seen_names:
            raise ValueError(f"Duplicate replacement candidate: {name}")
        seen_names.add(normalized_name)
        candidates.append(
            ReplacementCandidate(
                name=name,
                summary=summary,
                adaptation_notes=[
                    note.strip() for note in candidate.adaptation_notes if note.strip()
                ],
                reason=candidate.reason.strip() if candidate.reason else None,
            ),
        )

    if len(candidates) != 3:
        raise ValueError("AI must return exactly 3 replacement candidates")
    return candidates


def _parse_adjustment_payload(raw_content: str) -> ReplacementCandidate:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"AI returned invalid JSON for adjustment: {err}") from err

    try:
        parsed = _ReplacementCandidateModel.model_validate(payload)
    except ValidationError as err:
        raise ValueError(f"AI adjustment payload failed schema validation: {err}") from err

    name = parsed.name.strip()
    summary = parsed.summary.strip()
    if not name:
        raise ValueError("Adjusted dish has empty name")
    if not summary:
        raise ValueError("Adjusted dish has empty summary")

    return ReplacementCandidate(
        name=name,
        summary=summary,
        adaptation_notes=[note.strip() for note in parsed.adaptation_notes if note.strip()],
        reason=parsed.reason.strip() if parsed.reason else None,
    )


def _iter_dates(start_date: date, end_date: date) -> list[date]:
    current_date = start_date
    dates: list[date] = []
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)
    return dates


def _render_list(values: list[str]) -> str:
    return ", ".join(values) if values else "нет"


def _render_pantry(context: WeeklyPlanGenerationContext) -> str:
    if not context.pantry_items:
        return "учитывать pantry не нужно: список пуст"
    items_text = []
    for item in context.pantry_items:
        quantity_text = ""
        if item.quantity_value is not None:
            quantity_text = f", количество={item.quantity_value}"
            if item.quantity_unit:
                quantity_text += f" {item.quantity_unit}"
        elif item.quantity_unit:
            quantity_text = f", единица={item.quantity_unit}"
        note_text = f", note={item.note}" if item.note else ""
        items_text.append(
            f"{item.ingredient_name} (stock={item.stock_level.value}{quantity_text}{note_text})",
        )
    return "; ".join(items_text)


def _render_reference_recipes(context: WeeklyPlanGenerationContext) -> str:
    if not context.reference_recipes:
        return "none"

    lines: list[str] = []
    for recipe in context.reference_recipes:
        ingredients_text = (
            ", ".join(ingredient.name for ingredient in recipe.ingredients[:5])
            or "no ingredient preview"
        )
        cuisines_text = ", ".join(recipe.cuisines) if recipe.cuisines else "n/a"
        diets_text = ", ".join(recipe.diets) if recipe.diets else "n/a"
        summary_text = recipe.summary or "no summary"
        lines.append(
            (
                f"- {recipe.title} [provider={recipe.provider} id={recipe.external_id}]: "
                f"cuisines={cuisines_text}; diets={diets_text}; "
                f"ready_in_minutes={recipe.ready_in_minutes or 'n/a'}; "
                f"servings={recipe.servings or 'n/a'}; "
                f"ingredients={ingredients_text}; summary={summary_text}"
            ),
        )
    return "\n".join(lines)


def _render_replacement_reference_recipes(reference_recipes: list[RecipeHint]) -> str:
    if not reference_recipes:
        return "none"
    lines = []
    for recipe in reference_recipes:
        ingredient_names = (
            ", ".join(ingredient.name for ingredient in recipe.ingredients[:5]) or "n/a"
        )
        lines.append(
            (
                f"- {recipe.title}: cuisines={_render_list(recipe.cuisines)}; "
                f"diets={_render_list(recipe.diets)}; "
                f"ingredients={ingredient_names}; "
                f"summary={recipe.summary or 'n/a'}"
            ),
        )
    return "\n".join(lines)
