from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from aimealplanner.infrastructure.db.enums import PantryStockLevel, ShoppingListAvailabilityStatus


@dataclass(frozen=True, slots=True)
class ShoppingSourceIngredientEntry:
    ingredient_id: UUID
    canonical_name: str
    shopping_category: str | None
    default_unit: str | None
    amount_text: str | None
    quantity_value: Decimal | None
    quantity_unit: str | None
    preparation_note: str | None
    dish_name: str


@dataclass(frozen=True, slots=True)
class ShoppingSourcePantryEntry:
    ingredient_id: UUID
    stock_level: PantryStockLevel
    quantity_value: Decimal | None
    quantity_unit: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class ShoppingSourceContext:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    ingredient_entries: list[ShoppingSourceIngredientEntry] = field(default_factory=list)
    pantry_entries: list[ShoppingSourcePantryEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ShoppingListItemDraft:
    ingredient_id: UUID
    display_name: str
    quantity_value: Decimal | None
    quantity_unit: str | None
    category: str | None
    availability_status: ShoppingListAvailabilityStatus
    note: str | None
    quantity_label: str | None


@dataclass(frozen=True, slots=True)
class ShoppingListResult:
    shopping_list_id: UUID
    weekly_plan_id: UUID
    version: int
    start_date: date
    end_date: date
    items: list[ShoppingListItemDraft]
