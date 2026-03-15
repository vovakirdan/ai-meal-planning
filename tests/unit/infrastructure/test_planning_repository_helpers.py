# ruff: noqa: RUF001
from __future__ import annotations

from decimal import Decimal

from aimealplanner.infrastructure.db.repositories.planning import (
    _normalize_shopping_storage_quantity,
    _truncate_optional_value,
)


def test_normalize_shopping_storage_quantity_drops_overlong_unit() -> None:
    quantity_value, quantity_unit = _normalize_shopping_storage_quantity(
        Decimal("1"),
        "шт. (около 500 г очищенной мякоти)",
    )

    assert quantity_value is None
    assert quantity_unit is None


def test_normalize_shopping_storage_quantity_keeps_short_unit() -> None:
    quantity_value, quantity_unit = _normalize_shopping_storage_quantity(
        Decimal("250"),
        "г",
    )

    assert quantity_value == Decimal("250")
    assert quantity_unit == "г"


def test_truncate_optional_value_limits_length() -> None:
    assert _truncate_optional_value("  овощи и зелень  ", 5) == "овощи"
