# ruff: noqa: RUF001
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.dto import StoredDraftPlan, StoredPlanReference
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)
from aimealplanner.application.planning.shopping_dto import (
    ShoppingListItemDraft,
    ShoppingListResult,
    ShoppingSourceContext,
    ShoppingSourceIngredientEntry,
    ShoppingSourcePantryEntry,
)
from aimealplanner.infrastructure.db.enums import (
    PantryStockLevel,
    ShoppingListAvailabilityStatus,
)

_AMOUNT_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(.+?)\s*$")


@dataclass
class _ShoppingAccumulator:
    ingredient_id: UUID
    display_name: str
    category: str | None
    quantities_by_unit: dict[str, Decimal]
    availability_status: ShoppingListAvailabilityStatus


class RecipeWarmupClient(Protocol):
    async def warm_plan_recipes(
        self,
        telegram_user_id: int,
        weekly_plan_id: UUID,
    ) -> int: ...


class ShoppingListService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        *,
        recipe_warmer: RecipeWarmupClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._recipe_warmer = recipe_warmer

    async def generate_for_latest_visible_week(self, telegram_user_id: int) -> ShoppingListResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            plan_reference = await _resolve_latest_visible_plan(repositories, household_id)
            if plan_reference is None:
                raise ValueError("Текущего плана пока нет. Сначала составь его через /plan.")

            source = await repositories.weekly_plan_repository.get_shopping_source(
                household_id,
                plan_reference.id,
            )
            if source is None:
                raise ValueError("Не удалось собрать данные для списка покупок.")
            if not source.ingredient_entries:
                if self._recipe_warmer is not None:
                    await self._recipe_warmer.warm_plan_recipes(
                        telegram_user_id,
                        plan_reference.id,
                    )
                    source = await repositories.weekly_plan_repository.get_shopping_source(
                        household_id,
                        plan_reference.id,
                    )
                if source is None or not source.ingredient_entries:
                    raise ValueError("В текущем плане пока нет ингредиентов для списка покупок.")

            items = _build_shopping_items(source)
            result = await repositories.weekly_plan_repository.create_shopping_list(
                source.weekly_plan_id,
                items,
            )
            await session.commit()
            return result


def render_shopping_list(result: ShoppingListResult) -> str:
    lines = [
        "Список покупок.",
        (
            f"Период: {result.start_date.strftime('%d.%m.%Y')} - "
            f"{result.end_date.strftime('%d.%m.%Y')}."
        ),
    ]
    if not result.items:
        lines.extend(["", "Покупки для этой недели не нужны."])
        return "\n".join(lines)

    section_definitions = [
        (ShoppingListAvailabilityStatus.NEED_TO_BUY, "Купить"),
        (ShoppingListAvailabilityStatus.PARTIALLY_HAVE, "Проверить дома"),
    ]

    for availability_status, title in section_definitions:
        section_items = [
            item for item in result.items if item.availability_status is availability_status
        ]
        if not section_items:
            continue
        lines.extend(["", f"{title}:"])
        for item in section_items:
            line = f"- {item.display_name}"
            if item.quantity_label:
                line += f" — {item.quantity_label}"
            lines.append(line)
    return "\n".join(lines)


async def _resolve_household_id(
    repositories: PlanningRepositories,
    telegram_user_id: int,
) -> UUID:
    user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
    if user is None:
        raise ValueError("Профиль не найден. Сначала отправь /start.")

    household = await repositories.household_repository.get_by_user_id(user.id)
    if household is None or household.onboarding_completed_at is None:
        raise ValueError("Сначала заверши стартовую настройку через /start.")
    return household.id


async def _resolve_latest_visible_plan(
    repositories: PlanningRepositories,
    household_id: UUID,
) -> StoredDraftPlan | StoredPlanReference | None:
    latest_draft = await repositories.weekly_plan_repository.get_latest_draft_for_household(
        household_id,
    )
    if latest_draft is not None:
        return latest_draft
    return await repositories.weekly_plan_repository.get_latest_confirmed_for_household(
        household_id,
    )


def _build_shopping_items(source: ShoppingSourceContext) -> list[ShoppingListItemDraft]:
    pantry_by_ingredient_id = {item.ingredient_id: item for item in source.pantry_entries}
    grouped_entries: dict[UUID, list[ShoppingSourceIngredientEntry]] = defaultdict(list)
    for entry in source.ingredient_entries:
        grouped_entries[entry.ingredient_id].append(entry)

    items: list[ShoppingListItemDraft] = []
    for ingredient_id, entries in grouped_entries.items():
        first_entry = entries[0]
        pantry_entry = pantry_by_ingredient_id.get(ingredient_id)
        accumulator = _ShoppingAccumulator(
            ingredient_id=ingredient_id,
            display_name=first_entry.canonical_name,
            category=first_entry.shopping_category,
            quantities_by_unit={},
            availability_status=_resolve_availability_status(
                pantry_entry.stock_level if pantry_entry is not None else None,
            ),
        )
        for entry in entries:
            _accumulate_entry(accumulator, entry)

        remaining_quantities, availability_status = _resolve_remaining_quantities(
            accumulator.quantities_by_unit,
            pantry_entry,
        )
        if (
            not remaining_quantities
            and availability_status is ShoppingListAvailabilityStatus.ALREADY_HAVE
        ):
            continue
        quantity_value, quantity_unit, quantity_label = _resolve_quantity_summary(
            remaining_quantities,
        )
        items.append(
            ShoppingListItemDraft(
                ingredient_id=ingredient_id,
                display_name=accumulator.display_name,
                quantity_value=quantity_value,
                quantity_unit=quantity_unit,
                category=accumulator.category,
                availability_status=availability_status,
                note=None,
                quantity_label=quantity_label,
            ),
        )

    return sorted(
        items,
        key=lambda item: (
            _availability_order(item.availability_status),
            (item.category or "прочее").casefold(),
            item.display_name.casefold(),
        ),
    )


def _resolve_availability_status(
    stock_level: PantryStockLevel | None,
) -> ShoppingListAvailabilityStatus:
    if stock_level is PantryStockLevel.HAS:
        return ShoppingListAvailabilityStatus.ALREADY_HAVE
    if stock_level is PantryStockLevel.LOW:
        return ShoppingListAvailabilityStatus.PARTIALLY_HAVE
    return ShoppingListAvailabilityStatus.NEED_TO_BUY


def _accumulate_entry(
    accumulator: _ShoppingAccumulator,
    entry: ShoppingSourceIngredientEntry,
) -> None:
    parsed_amount = _resolve_entry_amount(entry)
    if parsed_amount is not None:
        value, unit = parsed_amount
        accumulator.quantities_by_unit[unit] = (
            accumulator.quantities_by_unit.get(unit, Decimal("0")) + value
        )


def _resolve_entry_amount(
    entry: ShoppingSourceIngredientEntry,
) -> tuple[Decimal, str] | None:
    if entry.quantity_value is not None and entry.quantity_unit:
        return entry.quantity_value, entry.quantity_unit.strip()
    if entry.amount_text is None:
        return None
    match = _AMOUNT_PATTERN.match(entry.amount_text)
    if match is None:
        return None
    raw_value, raw_unit = match.groups()
    try:
        value = Decimal(raw_value.replace(",", "."))
    except InvalidOperation:
        return None
    unit = raw_unit.strip()
    if not unit:
        unit = entry.default_unit or "шт"
    return value, unit


def _resolve_quantity_summary(
    quantities_by_unit: dict[str, Decimal],
) -> tuple[Decimal | None, str | None, str | None]:
    if not quantities_by_unit:
        return None, None, None
    if len(quantities_by_unit) == 1:
        unit, value = next(iter(quantities_by_unit.items()))
        return value, unit, f"{_format_decimal(value)} {unit}"
    quantity_bits = [
        f"{_format_decimal(value)} {unit}" for unit, value in sorted(quantities_by_unit.items())
    ]
    return None, None, ", ".join(quantity_bits)


def _resolve_remaining_quantities(
    required_quantities: dict[str, Decimal],
    pantry_entry: ShoppingSourcePantryEntry | None,
) -> tuple[dict[str, Decimal], ShoppingListAvailabilityStatus]:
    remaining_quantities = dict(required_quantities)
    if pantry_entry is None:
        return remaining_quantities, ShoppingListAvailabilityStatus.NEED_TO_BUY

    if pantry_entry.quantity_value is not None and pantry_entry.quantity_unit:
        pantry_unit = pantry_entry.quantity_unit.strip()
        required_value = remaining_quantities.get(pantry_unit)
        if required_value is not None:
            remaining_value = required_value - pantry_entry.quantity_value
            if remaining_value > 0:
                remaining_quantities[pantry_unit] = remaining_value
                return remaining_quantities, ShoppingListAvailabilityStatus.NEED_TO_BUY
            remaining_quantities.pop(pantry_unit, None)
            if remaining_quantities:
                return remaining_quantities, ShoppingListAvailabilityStatus.NEED_TO_BUY
            return {}, ShoppingListAvailabilityStatus.ALREADY_HAVE

    if pantry_entry.stock_level is PantryStockLevel.HAS:
        return remaining_quantities, ShoppingListAvailabilityStatus.PARTIALLY_HAVE
    if pantry_entry.stock_level is PantryStockLevel.LOW:
        return remaining_quantities, ShoppingListAvailabilityStatus.PARTIALLY_HAVE
    return remaining_quantities, ShoppingListAvailabilityStatus.NEED_TO_BUY


def _availability_order(value: ShoppingListAvailabilityStatus) -> int:
    return {
        ShoppingListAvailabilityStatus.NEED_TO_BUY: 0,
        ShoppingListAvailabilityStatus.PARTIALLY_HAVE: 1,
        ShoppingListAvailabilityStatus.ALREADY_HAVE: 2,
    }[value]


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").rstrip("0").rstrip(".")
