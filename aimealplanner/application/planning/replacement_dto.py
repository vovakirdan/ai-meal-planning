from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.generation_dto import (
    RecipeHint,
    WeeklyPlanGenerationContext,
)


@dataclass(frozen=True, slots=True)
class ReplacementCandidate:
    name: str
    summary: str
    adaptation_notes: list[str]
    reason: str | None


@dataclass(frozen=True, slots=True)
class ReplacementSuggestionResult:
    item_view: StoredPlanItemView
    generation_context: WeeklyPlanGenerationContext
    candidates: list[ReplacementCandidate]
    reference_recipes: list[RecipeHint]


@dataclass(frozen=True, slots=True)
class PlannedMealItemReplacement:
    planned_meal_item_id: UUID
    name: str
    summary: str
    adaptation_notes: list[str]
    snapshot_payload: dict[str, object]
