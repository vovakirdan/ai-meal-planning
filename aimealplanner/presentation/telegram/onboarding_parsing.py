from __future__ import annotations

import re
from datetime import time
from decimal import Decimal, InvalidOperation

_WHITESPACE_PATTERN = re.compile(r"\s+")
_LIST_SPLIT_PATTERN = re.compile(r"[,;\n]+")
_QUANTITY_PATTERN = re.compile(
    r"^\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>[^\d\s].*)\s*$",
)
_DAY_OF_WEEK_BY_LABEL = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}


def normalize_name(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value.strip()).lower()


def split_list_input(value: str) -> list[str]:
    parts = _LIST_SPLIT_PATTERN.split(value.strip())
    return [item.strip() for item in parts if item.strip()]


def parse_time_input(value: str) -> time:
    normalized = value.strip()
    try:
        hours_text, minutes_text = normalized.split(":", maxsplit=1)
    except ValueError as err:
        raise ValueError("Время нужно указать в формате ЧЧ:ММ, например 19:30.") from err

    if not hours_text.isdigit() or not minutes_text.isdigit():
        raise ValueError("Время нужно указать цифрами в формате ЧЧ:ММ.")

    hours = int(hours_text)
    minutes = int(minutes_text)
    if hours not in range(24) or minutes not in range(60):
        raise ValueError("Время должно быть в пределах 00:00-23:59.")

    return time(hour=hours, minute=minutes)


def parse_day_of_week(value: str) -> int:
    normalized = normalize_name(value)
    if normalized not in _DAY_OF_WEEK_BY_LABEL:
        allowed_days = ", ".join(day.title() for day in _DAY_OF_WEEK_BY_LABEL)
        raise ValueError(f"Выбери день недели из списка: {allowed_days}.")
    return _DAY_OF_WEEK_BY_LABEL[normalized]


def parse_quantity_hint(value: str) -> tuple[Decimal | None, str | None, str | None]:
    normalized = value.strip()
    if not normalized:
        return None, None, None

    match = _QUANTITY_PATTERN.match(normalized)
    if match is None:
        return None, None, normalized

    value_text = match.group("value").replace(",", ".")
    try:
        quantity_value = Decimal(value_text)
    except InvalidOperation as err:
        raise ValueError("Не удалось распознать количество продукта.") from err

    return quantity_value, match.group("unit").strip(), None
