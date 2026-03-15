from datetime import date

import pytest
from aimealplanner.presentation.telegram.planning_parsing import parse_date_input


def test_parse_date_input_accepts_iso_date() -> None:
    assert parse_date_input("2026-03-25", reference_year=2026) == date(2026, 3, 25)


def test_parse_date_input_accepts_russian_date_with_year() -> None:
    assert parse_date_input("25.03.2026", reference_year=2025) == date(2026, 3, 25)


def test_parse_date_input_accepts_day_and_month_using_reference_year() -> None:
    assert parse_date_input("25.03", reference_year=2026) == date(2026, 3, 25)


def test_parse_date_input_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        parse_date_input("32.03.2026", reference_year=2026)
