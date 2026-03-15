# ruff: noqa: RUF001
from __future__ import annotations

from uuid import UUID

from aimealplanner.application.settings.dto import (
    StoredSettingsDishPolicy,
    StoredSettingsMember,
    StoredSettingsPantryItem,
)
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict, RepeatabilityMode
from aimealplanner.presentation.telegram.keyboards.onboarding import DAY_OF_WEEK_LABELS
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CLEAR_LABEL = "Очистить"

_SETTINGS_HOME_CALLBACK = "sth"
_SETTINGS_SECTION_PREFIX = "sts"
_SETTINGS_FAMILY_MEMBER_PREFIX = "stf"
_SETTINGS_MEMBER_PREFIX = "stm"
_SETTINGS_PLANNING_PREFIX = "stp"
_SETTINGS_REMINDER_PREFIX = "str"
_SETTINGS_WEEKDAY_PREFIX = "stw"
_SETTINGS_PANTRY_PREFIX = "sty"
_SETTINGS_POLICY_PREFIX = "std"
_PANTRY_PAGE_SIZE = 8


def build_settings_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Семья",
                    callback_data=build_settings_section_callback("family"),
                ),
                InlineKeyboardButton(
                    text="Участники",
                    callback_data=build_settings_section_callback("members"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Планирование",
                    callback_data=build_settings_section_callback("planning"),
                ),
                InlineKeyboardButton(
                    text="Напоминания",
                    callback_data=build_settings_section_callback("reminders"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Запасы",
                    callback_data=build_settings_section_callback("pantry"),
                ),
                InlineKeyboardButton(
                    text="Блюда",
                    callback_data=build_settings_section_callback("policies"),
                ),
            ],
        ],
    )


def build_settings_family_keyboard(
    active_members: list[StoredSettingsMember],
    inactive_members: list[StoredSettingsMember],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Добавить участника",
                callback_data=build_family_add_callback(),
            ),
        ],
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=f"Активен · {member.display_name}",
                    callback_data=build_family_member_callback(member.id),
                ),
            ]
            for member in active_members
        ],
    )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=f"Отключен · {member.display_name}",
                    callback_data=build_family_member_callback(member.id),
                ),
            ]
            for member in inactive_members
        ],
    )
    rows.append([_back_button("К настройкам", build_settings_home_callback())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_family_member_keyboard(
    member_id: UUID,
    *,
    is_active: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Переименовать",
                callback_data=build_family_member_action_callback(member_id, "rename"),
            ),
        ],
        [
            InlineKeyboardButton(
                text="Отключить" if is_active else "Включить",
                callback_data=build_family_member_action_callback(
                    member_id,
                    "disable" if is_active else "enable",
                ),
            ),
        ],
        [_back_button("К составу семьи", build_settings_section_callback("family"))],
        [_back_button("К настройкам", build_settings_home_callback())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_settings_members_keyboard(
    members: list[StoredSettingsMember],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=member.display_name,
                callback_data=build_member_callback(member.id),
            ),
        ]
        for member in members
    ]
    rows.append([_back_button("К настройкам", build_settings_home_callback())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_member_detail_keyboard(member_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить ограничения",
                    callback_data=build_member_action_callback(member_id, "constraints"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить любимые кухни",
                    callback_data=build_member_action_callback(member_id, "cuisines"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить заметку",
                    callback_data=build_member_action_callback(member_id, "note"),
                ),
            ],
            [_back_button("К участникам", build_settings_section_callback("members"))],
            [_back_button("К настройкам", build_settings_home_callback())],
        ],
    )


def build_settings_planning_keyboard(
    *,
    meal_count_per_day: int,
    desserts_enabled: bool,
    repeatability_mode: RepeatabilityMode,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_mark_current(f"{value} приема", meal_count_per_day == value),
                callback_data=build_planning_callback("meal", str(value)),
            )
            for value in (2, 3, 4, 5)
        ],
        [
            InlineKeyboardButton(
                text=_mark_current("Десерты: Да", desserts_enabled),
                callback_data=build_planning_callback("desserts", "yes"),
            ),
            InlineKeyboardButton(
                text=_mark_current("Десерты: Нет", not desserts_enabled),
                callback_data=build_planning_callback("desserts", "no"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=_mark_current(
                    "Сбалансировано",
                    repeatability_mode is RepeatabilityMode.BALANCED,
                ),
                callback_data=build_planning_callback(
                    "repeatability",
                    RepeatabilityMode.BALANCED.value,
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=_mark_current(
                    "Больше нового",
                    repeatability_mode is RepeatabilityMode.MORE_VARIETY,
                ),
                callback_data=build_planning_callback(
                    "repeatability",
                    RepeatabilityMode.MORE_VARIETY.value,
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=_mark_current(
                    "Больше повторов",
                    repeatability_mode is RepeatabilityMode.MORE_REPEATABILITY,
                ),
                callback_data=build_planning_callback(
                    "repeatability",
                    RepeatabilityMode.MORE_REPEATABILITY.value,
                ),
            ),
        ],
        [_back_button("К настройкам", build_settings_home_callback())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_settings_reminders_keyboard(
    *,
    daily_enabled: bool,
    daily_time_text: str,
    weekly_enabled: bool,
    weekly_day_text: str,
    weekly_time_text: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Выключить ежедневное" if daily_enabled else "Включить ежедневное",
                callback_data=build_reminder_callback(
                    "daily",
                    "off" if daily_enabled else "on",
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"Время ежедневного: {daily_time_text}",
                callback_data=build_reminder_callback("daily", "time"),
            ),
        ],
        [
            InlineKeyboardButton(
                text="Выключить еженедельное" if weekly_enabled else "Включить еженедельное",
                callback_data=build_reminder_callback(
                    "weekly",
                    "off" if weekly_enabled else "on",
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"День еженедельного: {weekly_day_text}",
                callback_data=build_reminder_callback("weekly", "day"),
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"Время еженедельного: {weekly_time_text}",
                callback_data=build_reminder_callback("weekly", "time"),
            ),
        ],
        [_back_button("К настройкам", build_settings_home_callback())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_weekday_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=DAY_OF_WEEK_LABELS[index],
                callback_data=build_weekday_callback(index),
            ),
        ]
        for index in range(7)
    ]
    rows.append([_back_button("Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_settings_pantry_keyboard(
    items: list[StoredSettingsPantryItem],
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    page_items, total_pages = _paginate_items(items, page=page)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Добавить продукт",
                callback_data=build_pantry_callback("add"),
            ),
        ],
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=item.ingredient_name,
                    callback_data=build_pantry_item_callback(item.id, page=page),
                ),
            ]
            for item in page_items
        ],
    )
    if total_pages > 1:
        navigation_row: list[InlineKeyboardButton] = []
        if page > 0:
            navigation_row.append(
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=build_pantry_page_callback(page - 1),
                ),
            )
        navigation_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=build_pantry_page_callback(page),
            ),
        )
        if page + 1 < total_pages:
            navigation_row.append(
                InlineKeyboardButton(
                    text="Вперед ▶️",
                    callback_data=build_pantry_page_callback(page + 1),
                ),
            )
        rows.append(navigation_row)
    rows.append([_back_button("К настройкам", build_settings_home_callback())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_pantry_item_keyboard(pantry_item_id: UUID, *, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Есть",
                    callback_data=build_pantry_stock_callback(
                        pantry_item_id,
                        "has",
                        page=page,
                    ),
                ),
                InlineKeyboardButton(
                    text="Мало",
                    callback_data=build_pantry_stock_callback(
                        pantry_item_id,
                        "low",
                        page=page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить пометку",
                    callback_data=build_pantry_hint_callback(pantry_item_id, page=page),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Удалить из запасов",
                    callback_data=build_pantry_delete_callback(pantry_item_id, page=page),
                ),
            ],
            [_back_button("К запасам", build_pantry_page_callback(page))],
            [_back_button("К настройкам", build_settings_home_callback())],
        ],
    )


def build_pantry_stock_choice_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Есть",
                    callback_data=build_pantry_callback("stock:has"),
                ),
                InlineKeyboardButton(
                    text="Мало",
                    callback_data=build_pantry_callback("stock:low"),
                ),
            ],
            [_back_button("Назад", back_callback)],
        ],
    )


def build_settings_policy_home_keyboard(
    *,
    favorite_count: int,
    blocked_count: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Любимые ({favorite_count})",
                    callback_data=build_policy_list_callback(
                        DishFeedbackVerdict.FAVORITE,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"Не предлагать ({blocked_count})",
                    callback_data=build_policy_list_callback(
                        DishFeedbackVerdict.NEVER_AGAIN,
                    ),
                ),
            ],
            [_back_button("К настройкам", build_settings_home_callback())],
        ],
    )


def build_policy_list_keyboard(
    verdict: DishFeedbackVerdict,
    items: list[StoredSettingsDishPolicy],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=item.dish_name,
                callback_data=build_policy_item_callback(item.id),
            ),
        ]
        for item in items
    ]
    rows.append([_back_button("К правилам", build_settings_section_callback("policies"))])
    rows.append([_back_button("К настройкам", build_settings_home_callback())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_policy_detail_keyboard(
    *,
    policy_id: UUID,
    verdict: DishFeedbackVerdict,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Убрать правило",
                    callback_data=build_policy_remove_callback(policy_id),
                ),
            ],
            [_back_button("К списку", build_policy_list_callback(verdict))],
            [_back_button("К настройкам", build_settings_home_callback())],
        ],
    )


def build_prompt_back_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_back_button("Отмена", back_callback)]],
    )


def build_settings_home_callback() -> str:
    return _SETTINGS_HOME_CALLBACK


def build_settings_section_callback(section: str) -> str:
    return f"{_SETTINGS_SECTION_PREFIX}:{section}"


def build_family_add_callback() -> str:
    return f"{_SETTINGS_FAMILY_MEMBER_PREFIX}:add"


def build_family_member_callback(member_id: UUID) -> str:
    return f"{_SETTINGS_FAMILY_MEMBER_PREFIX}:member:{member_id.hex}"


def build_family_member_action_callback(member_id: UUID, action: str) -> str:
    return f"{_SETTINGS_FAMILY_MEMBER_PREFIX}:action:{member_id.hex}:{action}"


def build_member_callback(member_id: UUID) -> str:
    return f"{_SETTINGS_MEMBER_PREFIX}:detail:{member_id.hex}"


def build_member_action_callback(member_id: UUID, action: str) -> str:
    return f"{_SETTINGS_MEMBER_PREFIX}:action:{member_id.hex}:{action}"


def build_planning_callback(setting: str, value: str) -> str:
    return f"{_SETTINGS_PLANNING_PREFIX}:{setting}:{value}"


def build_reminder_callback(scope: str, action: str) -> str:
    return f"{_SETTINGS_REMINDER_PREFIX}:{scope}:{action}"


def build_weekday_callback(day_of_week: int) -> str:
    return f"{_SETTINGS_WEEKDAY_PREFIX}:{day_of_week}"


def build_pantry_callback(action: str) -> str:
    return f"{_SETTINGS_PANTRY_PREFIX}:{action}"


def build_pantry_page_callback(page: int) -> str:
    return f"{_SETTINGS_PANTRY_PREFIX}:page:{page}"


def build_pantry_item_callback(pantry_item_id: UUID, *, page: int = 0) -> str:
    return f"{_SETTINGS_PANTRY_PREFIX}:item:{pantry_item_id.hex}:{page}"


def build_pantry_stock_callback(pantry_item_id: UUID, stock_level: str, *, page: int = 0) -> str:
    return f"{_SETTINGS_PANTRY_PREFIX}:stock:{pantry_item_id.hex}:{stock_level}:{page}"


def build_pantry_hint_callback(pantry_item_id: UUID, *, page: int = 0) -> str:
    return f"{_SETTINGS_PANTRY_PREFIX}:hint:{pantry_item_id.hex}:{page}"


def build_pantry_delete_callback(pantry_item_id: UUID, *, page: int = 0) -> str:
    return f"{_SETTINGS_PANTRY_PREFIX}:delete:{pantry_item_id.hex}:{page}"


def build_policy_list_callback(verdict: DishFeedbackVerdict) -> str:
    return f"{_SETTINGS_POLICY_PREFIX}:list:{verdict.value}"


def build_policy_item_callback(policy_id: UUID) -> str:
    return f"{_SETTINGS_POLICY_PREFIX}:item:{policy_id.hex}"


def build_policy_remove_callback(policy_id: UUID) -> str:
    return f"{_SETTINGS_POLICY_PREFIX}:remove:{policy_id.hex}"


def parse_settings_section_callback(value: str) -> str | None:
    prefix, _, section = value.partition(":")
    if prefix != _SETTINGS_SECTION_PREFIX or not section:
        return None
    return section


def parse_family_callback(value: str) -> tuple[str, UUID | None] | None:
    parts = value.split(":")
    if not parts or parts[0] != _SETTINGS_FAMILY_MEMBER_PREFIX:
        return None
    if len(parts) == 2 and parts[1] == "add":
        return ("add", None)
    if len(parts) == 3 and parts[1] == "member":
        return ("member", _parse_uuid(parts[2]))
    if len(parts) == 4 and parts[1] == "action":
        return (parts[3], _parse_uuid(parts[2]))
    return None


def parse_member_callback(value: str) -> tuple[str, UUID | None] | None:
    parts = value.split(":")
    if not parts or parts[0] != _SETTINGS_MEMBER_PREFIX:
        return None
    if len(parts) == 3 and parts[1] == "detail":
        return ("detail", _parse_uuid(parts[2]))
    if len(parts) == 4 and parts[1] == "action":
        return (parts[3], _parse_uuid(parts[2]))
    return None


def parse_planning_callback(value: str) -> tuple[str, str] | None:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != _SETTINGS_PLANNING_PREFIX:
        return None
    return parts[1], parts[2]


def parse_reminder_callback(value: str) -> tuple[str, str] | None:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != _SETTINGS_REMINDER_PREFIX:
        return None
    return parts[1], parts[2]


def parse_weekday_callback(value: str) -> int | None:
    parts = value.split(":")
    if len(parts) != 2 or parts[0] != _SETTINGS_WEEKDAY_PREFIX:
        return None
    if not parts[1].isdigit():
        return None
    day_of_week = int(parts[1])
    if day_of_week not in range(7):
        return None
    return day_of_week


def parse_pantry_callback(value: str) -> tuple[str, UUID | None, str | None, int | None] | None:
    parts = value.split(":")
    if not parts or parts[0] != _SETTINGS_PANTRY_PREFIX:
        return None
    if len(parts) == 2:
        return parts[1], None, None, None
    if len(parts) == 3 and parts[1] == "page" and parts[2].isdigit():
        return ("page", None, None, int(parts[2]))
    if len(parts) == 4 and parts[1] in {"item", "hint", "delete"} and parts[3].isdigit():
        return parts[1], _parse_uuid(parts[2]), None, int(parts[3])
    if len(parts) == 5 and parts[1] == "stock" and parts[4].isdigit():
        return parts[1], _parse_uuid(parts[2]), parts[3], int(parts[4])
    return None


def parse_policy_callback(value: str) -> tuple[str, DishFeedbackVerdict | UUID | None] | None:
    parts = value.split(":")
    if not parts or parts[0] != _SETTINGS_POLICY_PREFIX:
        return None
    if len(parts) == 3 and parts[1] == "list":
        try:
            return ("list", DishFeedbackVerdict(parts[2]))
        except ValueError:
            return None
    if len(parts) == 3 and parts[1] in {"item", "remove"}:
        return (parts[1], _parse_uuid(parts[2]))
    return None


def _back_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _mark_current(label: str, is_current: bool) -> str:
    return f"• {label}" if is_current else label


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(hex=value)
    except ValueError:
        return None


def _paginate_items(
    items: list[StoredSettingsPantryItem],
    *,
    page: int,
) -> tuple[list[StoredSettingsPantryItem], int]:
    total_pages = max(1, (len(items) + _PANTRY_PAGE_SIZE - 1) // _PANTRY_PAGE_SIZE)
    clamped_page = max(0, min(page, total_pages - 1))
    start_index = clamped_page * _PANTRY_PAGE_SIZE
    end_index = start_index + _PANTRY_PAGE_SIZE
    return items[start_index:end_index], total_pages
