from __future__ import annotations

from datetime import date


def parse_date_input(value: str, *, reference_year: int) -> date:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Нужна дата. Пример: 25.03.2026 или 2026-03-25.")

    if "-" in normalized:
        try:
            return date.fromisoformat(normalized)
        except ValueError as err:
            raise ValueError("Не удалось прочитать дату. Пример: 2026-03-25.") from err

    parts = normalized.split(".")
    if len(parts) == 2:
        day_text, month_text = parts
        year = reference_year
    elif len(parts) == 3:
        day_text, month_text, year_text = parts
        year = _parse_numeric_part(year_text, "год")
    else:
        raise ValueError("Нужна дата в формате ДД.ММ.ГГГГ или 2026-03-25.")

    day = _parse_numeric_part(day_text, "день")
    month = _parse_numeric_part(month_text, "месяц")
    try:
        return date(year=year, month=month, day=day)
    except ValueError as err:
        raise ValueError("Такой даты не существует. Проверь день и месяц.") from err


def _parse_numeric_part(value: str, part_name: str) -> int:
    if not value.isdigit():
        raise ValueError(f"Не удалось прочитать {part_name} в дате.")
    return int(value)
