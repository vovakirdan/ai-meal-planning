from decimal import Decimal

import pytest
from aimealplanner.presentation.telegram.onboarding_parsing import (
    normalize_name,
    parse_day_of_week,
    parse_quantity_hint,
    parse_time_input,
    split_list_input,
)


def test_split_list_input_handles_commas_and_newlines() -> None:
    assert split_list_input("оливки, печень\nкинза") == ["оливки", "печень", "кинза"]


def test_parse_time_input_validates_shape() -> None:
    with pytest.raises(ValueError):
        parse_time_input("25:10")

    assert parse_time_input("09:30").isoformat() == "09:30:00"


def test_parse_day_of_week_accepts_russian_labels() -> None:
    assert parse_day_of_week("Пятница") == 4


def test_parse_quantity_hint_extracts_numeric_quantity() -> None:
    assert parse_quantity_hint("500 г") == (Decimal("500"), "г", None)
    assert parse_quantity_hint("примерно полбанки") == (None, None, "примерно полбанки")


def test_normalize_name_collapses_whitespace() -> None:
    assert normalize_name("  Томаты   в  собственном соку  ") == "томаты в собственном соку"
