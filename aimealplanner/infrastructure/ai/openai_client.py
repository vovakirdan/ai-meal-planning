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
    DishQuickAction,
    GeneratedMeal,
    GeneratedMealItem,
    GeneratedWeekPlan,
    HouseholdDishPolicyContext,
    RecipeHint,
    WeeklyPlanGenerationContext,
)
from aimealplanner.application.planning.recipe_dto import (
    RecipeDetails,
    RecipeIngredient,
)
from aimealplanner.application.planning.replacement_dto import ReplacementCandidate
from aimealplanner.core.config import Settings
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict

logger = logging.getLogger(__name__)


class _GeneratedMealItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    adaptation_notes: list[str] = Field(default_factory=list)
    suggested_actions: list[_QuickActionModel] = Field(default_factory=list)


class _QuickActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    instruction: str


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
    suggested_actions: list[_QuickActionModel] = Field(default_factory=list)
    reason: str | None = None


class _ReplacementCandidatesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[_ReplacementCandidateModel]


class _PolicyReasonModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_note: str | None = None


class _FeedbackCommentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planning_note: str | None = None
    restriction_candidate: str | None = None


class _RecipeIngredientModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    amount: str | None = None
    preparation_note: str | None = None


class _RecipeDetailsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    ingredients: list[_RecipeIngredientModel] = Field(default_factory=list)
    preparation_steps: list[str] = Field(default_factory=list)
    cooking_steps: list[str] = Field(default_factory=list)
    serving_steps: list[str] = Field(default_factory=list)
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    serving_notes: str | None = None


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
            return _parse_replacement_payload(raw_content, slot=item_view.slot)
        except ValueError as err:
            logger.warning("replacement payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_REPLACEMENT_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_replacement_payload(repaired_content, slot=item_view.slot)

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
            return _parse_adjustment_payload(raw_content, slot=item_view.slot)
        except ValueError as err:
            logger.warning("adjustment payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_ADJUSTMENT_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_adjustment_payload(repaired_content, slot=item_view.slot)

    async def normalize_policy_reason(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        verdict_label: str,
        raw_reason: str,
    ) -> str | None:
        raw_content = await self._request_json(
            system_prompt=_POLICY_REASON_SYSTEM_PROMPT,
            user_prompt=_build_policy_reason_prompt(
                item_view=item_view,
                generation_context=generation_context,
                verdict_label=verdict_label,
                raw_reason=raw_reason,
            ),
        )
        try:
            return _parse_policy_reason_payload(raw_content)
        except ValueError as err:
            logger.warning("policy reason payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_POLICY_REASON_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_policy_reason_payload(repaired_content)

    async def normalize_feedback_comment(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        household_member_name: str,
        verdict: DishFeedbackVerdict,
        raw_comment: str,
    ) -> dict[str, object]:
        raw_content = await self._request_json(
            system_prompt=_FEEDBACK_COMMENT_SYSTEM_PROMPT,
            user_prompt=_build_feedback_comment_prompt(
                item_view=item_view,
                generation_context=generation_context,
                household_member_name=household_member_name,
                verdict=verdict,
                raw_comment=raw_comment,
            ),
        )
        try:
            return _parse_feedback_comment_payload(raw_content)
        except ValueError as err:
            logger.warning("feedback comment payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_FEEDBACK_COMMENT_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_feedback_comment_payload(repaired_content)

    async def expand_item_recipe(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        reference_recipes: list[RecipeHint],
    ) -> RecipeDetails:
        raw_content = await self._request_json(
            system_prompt=_RECIPE_DETAILS_SYSTEM_PROMPT,
            user_prompt=_build_recipe_details_prompt(
                item_view=item_view,
                generation_context=generation_context,
                reference_recipes=reference_recipes,
            ),
        )
        try:
            return _parse_recipe_details_payload(raw_content)
        except ValueError as err:
            logger.warning("recipe details payload validation failed, attempting repair: %s", err)
            repaired_content = await self._request_json(
                system_prompt=_RECIPE_DETAILS_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_recipe_details_payload(repaired_content)

    async def adjust_item_recipe(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        instruction: str,
        reference_recipes: list[RecipeHint],
    ) -> RecipeDetails:
        raw_content = await self._request_json(
            system_prompt=_RECIPE_DETAILS_SYSTEM_PROMPT,
            user_prompt=_build_recipe_adjustment_prompt(
                item_view=item_view,
                generation_context=generation_context,
                instruction=instruction,
                reference_recipes=reference_recipes,
            ),
        )
        try:
            return _parse_recipe_details_payload(raw_content)
        except ValueError as err:
            logger.warning(
                "recipe adjustment payload validation failed, attempting repair: %s",
                err,
            )
            repaired_content = await self._request_json(
                system_prompt=_RECIPE_DETAILS_SYSTEM_PROMPT,
                user_prompt=_build_replacement_repair_prompt(raw_content, str(err)),
            )
            return _parse_recipe_details_payload(repaired_content)

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


_POLICY_REASON_SYSTEM_PROMPT = """
You normalize short household feedback for a Telegram meal planner bot.
Return valid JSON only.
Do not use markdown fences.
Do not add commentary outside the JSON object.
Write the normalized note in Russian.
""".strip()


_FEEDBACK_COMMENT_SYSTEM_PROMPT = """
You normalize post-meal dish feedback for a Telegram meal planner bot.
Return valid JSON only.
Do not use markdown fences.
Do not add commentary outside the JSON object.
Write concise Russian planning notes.
""".strip()


_RECIPE_DETAILS_SYSTEM_PROMPT = """
You expand one dish into a practical home-cooking recipe for a Telegram meal planner bot.
Return valid JSON only.
Do not use markdown fences.
Do not add commentary outside the JSON object.
Keep recipe text in Russian.
""".strip()


def _build_week_plan_prompt(context: WeeklyPlanGenerationContext) -> str:
    pantry_text = "ignore pantry" if not context.pantry_considered else _render_pantry(context)
    reference_recipes_text = _render_reference_recipes(context)
    policy_text = _render_household_policies(context.household_policies)
    member_lines = _render_household_members(context)
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

Existing household dish memory:
{policy_text}

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
- suggested_actions must contain 2 short, context-aware improvement options for this specific dish.
- suggested_actions must fit the dish and slot.
- Example: dessert can be less sweet, but not less spicy.
- Each suggested_actions label should be 1-3 short Russian words for a Telegram button.

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
          "adaptation_notes": ["string"],
          "suggested_actions": [
            {{
              "label": "string",
              "instruction": "string"
            }}
          ]
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
    other_constraints = _render_household_members(generation_context)
    references_text = _render_replacement_reference_recipes(reference_recipes)
    policy_text = _render_household_policies(generation_context.household_policies)
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

Existing household dish memory:
{policy_text}

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
- suggested_actions must contain 2 short, context-aware improvement options
  for this specific replacement.

Required JSON shape:
{{
  "candidates": [
    {{
      "name": "string",
      "summary": "string",
      "adaptation_notes": ["string"],
      "suggested_actions": [
        {{
          "label": "string",
          "instruction": "string"
        }}
      ],
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
    policy_text = _render_household_policies(generation_context.household_policies)
    household_lines = _render_household_members(generation_context)
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

Existing household dish memory:
{policy_text}

Optional recipe references:
{references_text}

Requirements:
- Keep the dish suitable for the same meal slot.
- Preserve the core idea of the dish unless the instruction clearly asks for a stronger change.
- Avoid forbidden ingredients.
- Prefer practical household cooking over restaurant-style complexity.
- reason should briefly explain what changed.
- adaptation_notes should be an empty list if there are no special adjustments.
- suggested_actions must contain 2 short, context-aware improvement options for the adjusted dish.

Required JSON shape:
{{
  "name": "string",
  "summary": "string",
  "adaptation_notes": ["string"],
  "suggested_actions": [
    {{
      "label": "string",
      "instruction": "string"
    }}
  ],
  "reason": "string or null"
}}
""".strip()


def _build_policy_reason_prompt(
    *,
    item_view: StoredPlanItemView,
    generation_context: WeeklyPlanGenerationContext,
    verdict_label: str,
    raw_reason: str,
) -> str:
    return f"""
Normalize one household policy note for meal planning memory.

Dish:
- name: {item_view.name}
- summary: {item_view.summary or "нет"}
- slot: {item_view.slot}

Household context:
{_render_household_members(generation_context)}

Raw user reason:
- verdict: {verdict_label}
- reason: {raw_reason}

Requirements:
- Return a short Russian note for future planning.
- Preserve broader restrictions only if the user clearly indicated them.
- If the reason is vague or useless, return null.

Required JSON shape:
{{
  "policy_note": "string or null"
}}
""".strip()


def _build_feedback_comment_prompt(
    *,
    item_view: StoredPlanItemView,
    generation_context: WeeklyPlanGenerationContext,
    household_member_name: str,
    verdict: DishFeedbackVerdict,
    raw_comment: str,
) -> str:
    return f"""
Normalize one post-meal feedback comment for future meal planning.

Dish:
- name: {item_view.name}
- summary: {item_view.summary or "нет"}
- slot: {item_view.slot}

Household member:
- name: {household_member_name}

Household context:
{_render_household_members(generation_context)}

Raw feedback:
- verdict: {verdict.value}
- comment: {raw_comment}

Requirements:
- planning_note should be a short Russian memory for future planning.
- restriction_candidate should be set only if the comment clearly suggests
  a broader recurring preference or restriction, not just a one-off critique.
- Do not invent medical or religious restrictions.
- If the comment is only about this exact dish, restriction_candidate must be null.
- If the comment is too vague, planning_note may be null.

Required JSON shape:
{{
  "planning_note": "string or null",
  "restriction_candidate": "string or null"
}}
""".strip()


def _build_recipe_details_prompt(
    *,
    item_view: StoredPlanItemView,
    generation_context: WeeklyPlanGenerationContext,
    reference_recipes: list[RecipeHint],
) -> str:
    return f"""
Expand one weekly plan dish into a practical recipe.

Dish:
- name: {item_view.name}
- summary: {item_view.summary or "нет"}
- slot: {item_view.slot}
- meal_date: {item_view.meal_date.isoformat()}
- adaptation_notes: {_render_list(item_view.adaptation_notes)}

Household context:
{_render_household_members(generation_context)}

Week context:
- week_mood: {generation_context.week_mood or "без явного уклона"}
- weekly_notes: {generation_context.weekly_notes or "нет"}
- repeatability_mode: {generation_context.repeatability_mode.value}

Existing household dish memory:
{_render_household_policies(generation_context.household_policies)}

Optional recipe references:
{_render_replacement_reference_recipes(reference_recipes)}

Requirements:
- Build a realistic home recipe, not restaurant plating.
- Respect constraints and adaptation notes.
- ingredients should be concrete and usable for shopping.
- preparation_steps, cooking_steps and serving_steps may be empty lists if not needed,
  but ingredients must not be empty.
- Keep 3-8 ingredients for simple dishes, more only when clearly needed.
- Keep steps concise.
- prep_time_minutes and cook_time_minutes are optional integers.

Required JSON shape:
{{
  "summary": "string or null",
  "ingredients": [
    {{
      "name": "string",
      "amount": "string or null",
      "preparation_note": "string or null"
    }}
  ],
  "preparation_steps": ["string"],
  "cooking_steps": ["string"],
  "serving_steps": ["string"],
  "prep_time_minutes": 10,
  "cook_time_minutes": 20,
  "serving_notes": "string or null"
}}
""".strip()


def _build_recipe_adjustment_prompt(
    *,
    item_view: StoredPlanItemView,
    generation_context: WeeklyPlanGenerationContext,
    instruction: str,
    reference_recipes: list[RecipeHint],
) -> str:
    return f"""
Refine one existing recipe for a weekly plan dish after user feedback.

Dish:
- name: {item_view.name}
- summary: {item_view.summary or "нет"}
- slot: {item_view.slot}
- meal_date: {item_view.meal_date.isoformat()}
- adaptation_notes: {_render_list(item_view.adaptation_notes)}

Current saved recipe:
{_render_current_recipe_snapshot(item_view)}

Household context:
{_render_household_members(generation_context)}

Week context:
- week_mood: {generation_context.week_mood or "без явного уклона"}
- weekly_notes: {generation_context.weekly_notes or "нет"}
- repeatability_mode: {generation_context.repeatability_mode.value}

Existing household dish memory:
{_render_household_policies(generation_context.household_policies)}

Optional recipe references:
{_render_replacement_reference_recipes(reference_recipes)}

User correction request:
- instruction: {instruction}

Requirements:
- Keep the same core dish unless the user clearly asks for a deeper change.
- Fix the recipe logic according to the user's note.
- Preserve suitability for the same meal slot.
- Respect constraints and adaptation notes.
- ingredients should be concrete and usable for shopping.
- preparation_steps, cooking_steps and serving_steps may be empty lists if not needed,
  but ingredients must not be empty.
- Keep steps concise and practical for home cooking.
- prep_time_minutes and cook_time_minutes are optional integers.

Required JSON shape:
{{
  "summary": "string or null",
  "ingredients": [
    {{
      "name": "string",
      "amount": "string or null",
      "preparation_note": "string or null"
    }}
  ],
  "preparation_steps": ["string"],
  "cooking_steps": ["string"],
  "serving_steps": ["string"],
  "prep_time_minutes": 10,
  "cook_time_minutes": 20,
  "serving_notes": "string or null"
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
                    suggested_actions=_parse_quick_actions(
                        item.suggested_actions,
                        slot=meal.slot,
                        dish_name=name,
                    ),
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


def _parse_replacement_payload(raw_content: str, *, slot: str) -> list[ReplacementCandidate]:
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
                suggested_actions=_parse_quick_actions(
                    candidate.suggested_actions,
                    slot=slot,
                    dish_name=name,
                ),
                reason=candidate.reason.strip() if candidate.reason else None,
            ),
        )

    if len(candidates) != 3:
        raise ValueError("AI must return exactly 3 replacement candidates")
    return candidates


def _parse_adjustment_payload(raw_content: str, *, slot: str) -> ReplacementCandidate:
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
        suggested_actions=_parse_quick_actions(
            parsed.suggested_actions,
            slot=slot,
            dish_name=name,
        ),
        reason=parsed.reason.strip() if parsed.reason else None,
    )


def _parse_policy_reason_payload(raw_content: str) -> str | None:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"AI returned invalid JSON for policy reason: {err}") from err

    try:
        parsed = _PolicyReasonModel.model_validate(payload)
    except ValidationError as err:
        raise ValueError(f"AI policy reason payload failed schema validation: {err}") from err

    if parsed.policy_note is None:
        return None
    normalized_note = parsed.policy_note.strip()
    return normalized_note or None


def _parse_feedback_comment_payload(raw_content: str) -> dict[str, object]:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"AI returned invalid JSON for feedback comment: {err}") from err

    try:
        parsed = _FeedbackCommentModel.model_validate(payload)
    except ValidationError as err:
        raise ValueError(f"AI feedback comment payload failed schema validation: {err}") from err

    normalized_notes: dict[str, object] = {}
    if parsed.planning_note is not None:
        planning_note = parsed.planning_note.strip()
        if planning_note:
            normalized_notes["planning_note"] = planning_note
    if parsed.restriction_candidate is not None:
        restriction_candidate = parsed.restriction_candidate.strip()
        if restriction_candidate:
            normalized_notes["restriction_candidate"] = restriction_candidate
    return normalized_notes


def _parse_recipe_details_payload(raw_content: str) -> RecipeDetails:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"AI returned invalid JSON for recipe details: {err}") from err

    try:
        parsed = _RecipeDetailsModel.model_validate(payload)
    except ValidationError as err:
        raise ValueError(f"AI recipe details payload failed schema validation: {err}") from err

    ingredients: list[RecipeIngredient] = []
    seen_names: set[str] = set()
    for ingredient in parsed.ingredients:
        normalized_name = ingredient.name.strip().casefold()
        if not normalized_name or normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        ingredients.append(
            RecipeIngredient(
                name=ingredient.name.strip(),
                amount=ingredient.amount.strip() if isinstance(ingredient.amount, str) else None,
                preparation_note=(
                    ingredient.preparation_note.strip()
                    if isinstance(ingredient.preparation_note, str)
                    else None
                ),
            ),
        )

    if not ingredients:
        raise ValueError("Recipe details must include at least one ingredient")

    return RecipeDetails(
        summary=parsed.summary.strip() if isinstance(parsed.summary, str) else None,
        ingredients=ingredients,
        preparation_steps=_clean_step_list(parsed.preparation_steps),
        cooking_steps=_clean_step_list(parsed.cooking_steps),
        serving_steps=_clean_step_list(parsed.serving_steps),
        prep_time_minutes=parsed.prep_time_minutes,
        cook_time_minutes=parsed.cook_time_minutes,
        serving_notes=(
            parsed.serving_notes.strip() if isinstance(parsed.serving_notes, str) else None
        ),
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


def _render_household_members(context: WeeklyPlanGenerationContext) -> str:
    return "\n".join(
        [
            (
                f"- {member.display_name}: ограничения={_render_list(member.constraints)}, "
                f"любит={_render_list(member.favorite_cuisines)}, "
                f"заметка={member.profile_note or 'нет'}, "
                f"feedback={_render_list(member.feedback_notes)}"
            )
            for member in context.members
        ],
    )


def _render_household_policies(policies: list[HouseholdDishPolicyContext]) -> str:
    if not policies:
        return "none"
    return "\n".join(
        [
            f"- {policy.dish_name}: {policy.verdict.value}; note={policy.note or 'нет'}"
            for policy in policies
        ],
    )


def _parse_quick_actions(
    raw_actions: list[_QuickActionModel],
    *,
    slot: str,
    dish_name: str,
) -> list[DishQuickAction]:
    parsed_actions: list[DishQuickAction] = []
    seen_labels: set[str] = set()
    for action in raw_actions:
        label = action.label.strip()
        instruction = action.instruction.strip()
        if not label or not instruction:
            continue
        normalized_label = label.casefold()
        if normalized_label in seen_labels:
            continue
        seen_labels.add(normalized_label)
        parsed_actions.append(
            DishQuickAction(
                label=label[:24],
                instruction=instruction,
            ),
        )

    if len(parsed_actions) >= 2:
        return parsed_actions[:2]
    return _fallback_quick_actions(slot=slot, dish_name=dish_name)


def _fallback_quick_actions(*, slot: str, dish_name: str) -> list[DishQuickAction]:
    normalized_name = dish_name.casefold()
    if slot == "dessert":
        return [
            DishQuickAction(
                label="Менее сладким",
                instruction="Сделай десерт менее сладким, сохранив его общий характер.",
            ),
            DishQuickAction(
                label="Легче",
                instruction="Сделай десерт легче и менее тяжелым по ощущениям.",
            ),
        ]
    if slot == "breakfast":
        return [
            DishQuickAction(
                label="Сытнее",
                instruction="Сделай блюдо чуть более сытным для завтрака.",
            ),
            DishQuickAction(
                label="Легче",
                instruction="Сделай блюдо легче и мягче для утра.",
            ),
        ]
    if "суп" in normalized_name:
        return [
            DishQuickAction(
                label="Погуще",
                instruction="Сделай суп чуть гуще и насыщеннее.",
            ),
            DishQuickAction(
                label="Легче",
                instruction="Сделай суп легче и менее жирным.",
            ),
        ]
    return [
        DishQuickAction(
            label="Легче",
            instruction="Сделай блюдо легче и менее жирным, сохранив его основную идею.",
        ),
        DishQuickAction(
            label="Мягче вкус",
            instruction="Сделай вкус блюда мягче и менее резким, сохранив его идею.",
        ),
    ]


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


def _clean_step_list(steps: list[str]) -> list[str]:
    return [step.strip() for step in steps if step.strip()]


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


def _render_current_recipe_snapshot(item_view: StoredPlanItemView) -> str:
    payload = item_view.snapshot_payload
    ingredient_lines: list[str] = []
    raw_ingredients = payload.get("ingredients")
    if isinstance(raw_ingredients, list):
        for raw_ingredient in raw_ingredients:
            if not isinstance(raw_ingredient, dict):
                continue
            name = raw_ingredient.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            line = name.strip()
            amount = raw_ingredient.get("amount")
            if isinstance(amount, str) and amount.strip():
                line += f" — {amount.strip()}"
            note = raw_ingredient.get("preparation_note")
            if isinstance(note, str) and note.strip():
                line += f" ({note.strip()})"
            ingredient_lines.append(line)

    def render_steps(field_name: str) -> str:
        raw_steps = payload.get(field_name)
        if not isinstance(raw_steps, list):
            return "нет"
        normalized_steps = [
            step.strip() for step in raw_steps if isinstance(step, str) and step.strip()
        ]
        return "; ".join(normalized_steps) if normalized_steps else "нет"

    serving_notes = payload.get("serving_notes")
    prep_time = payload.get("prep_time_minutes")
    cook_time = payload.get("cook_time_minutes")
    return "\n".join(
        [
            f"- summary: {item_view.summary or 'нет'}",
            (
                f"- ingredients: {'; '.join(ingredient_lines)}"
                if ingredient_lines
                else "- ingredients: нет"
            ),
            f"- preparation_steps: {render_steps('preparation_steps')}",
            f"- cooking_steps: {render_steps('cooking_steps')}",
            f"- serving_steps: {render_steps('serving_steps')}",
            f"- prep_time_minutes: {prep_time if isinstance(prep_time, int) else 'нет'}",
            f"- cook_time_minutes: {cook_time if isinstance(cook_time, int) else 'нет'}",
            (
                f"- serving_notes: {serving_notes.strip()}"
                if isinstance(serving_notes, str) and serving_notes.strip()
                else "- serving_notes: нет"
            ),
        ],
    )
