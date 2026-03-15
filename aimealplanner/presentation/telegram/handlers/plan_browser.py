# ruff: noqa: RUF001
from __future__ import annotations

from datetime import date
from typing import cast

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning import PlanningBrowsingService
from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDayView,
    StoredPlanItemView,
    StoredPlanMealView,
)
from aimealplanner.infrastructure.db.repositories import build_planning_repositories
from aimealplanner.presentation.telegram.keyboards.onboarding import remove_keyboard
from aimealplanner.presentation.telegram.keyboards.planning import (
    build_plan_day_keyboard,
    build_plan_days_keyboard,
    build_plan_item_keyboard,
    build_plan_meal_keyboard,
    parse_plan_day_callback,
    parse_plan_item_callback,
    parse_plan_meal_callback,
    parse_plan_week_callback,
)


def build_plan_browser_router(
    session_factory: async_sessionmaker[AsyncSession],
) -> Router:
    router = Router(name="plan_browser")
    browsing_service = PlanningBrowsingService(session_factory, build_planning_repositories)

    @router.message(Command("week"))
    async def handle_week_command(message: Message) -> None:
        try:
            overview = await browsing_service.get_latest_draft_overview(
                _require_telegram_user_id_from_message(message),
            )
        except ValueError as err:
            await message.answer(str(err), reply_markup=remove_keyboard())
            return

        await message.answer(
            overview.text,
            reply_markup=build_plan_days_keyboard(
                overview.weekly_plan_id,
                overview.start_date,
                overview.end_date,
            ),
        )

    @router.callback_query(F.data.startswith("pw:"))
    async def handle_plan_week_callback(callback: CallbackQuery) -> None:
        callback_data = cast(str, callback.data)
        weekly_plan_id = parse_plan_week_callback(callback_data)
        if weekly_plan_id is None:
            await callback.answer("Не получилось прочитать выбранный план.", show_alert=True)
            return

        try:
            overview = await browsing_service.get_latest_draft_overview(
                _require_telegram_user_id_from_callback(callback),
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        if overview.weekly_plan_id != weekly_plan_id:
            await callback.answer("Открываю текущий актуальный черновик.")

        await _edit_callback_message(
            callback,
            text=overview.text,
            reply_markup=build_plan_days_keyboard(
                overview.weekly_plan_id,
                overview.start_date,
                overview.end_date,
            ),
        )

    @router.callback_query(F.data.startswith("pd:"))
    async def handle_plan_day_callback(callback: CallbackQuery) -> None:
        callback_data = cast(str, callback.data)
        parsed_value = parse_plan_day_callback(callback_data)
        if parsed_value is None:
            await callback.answer("Не получилось открыть выбранный день.", show_alert=True)
            return

        weekly_plan_id, meal_date = parsed_value
        try:
            day_view = await browsing_service.get_day_view(
                _require_telegram_user_id_from_callback(callback),
                weekly_plan_id,
                meal_date,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _edit_callback_message(
            callback,
            text=_render_day_view(day_view),
            reply_markup=build_plan_day_keyboard(
                day_view.weekly_plan_id,
                [
                    (meal.planned_meal_id, _render_meal_button_label(meal.slot, meal.item_names))
                    for meal in day_view.meals
                ],
            ),
        )

    @router.callback_query(F.data.startswith("pm:"))
    async def handle_plan_meal_callback(callback: CallbackQuery) -> None:
        callback_data = cast(str, callback.data)
        planned_meal_id = parse_plan_meal_callback(callback_data)
        if planned_meal_id is None:
            await callback.answer("Не получилось открыть прием пищи.", show_alert=True)
            return

        try:
            meal_view = await browsing_service.get_meal_view(
                _require_telegram_user_id_from_callback(callback),
                planned_meal_id,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _edit_callback_message(
            callback,
            text=_render_meal_view(meal_view),
            reply_markup=build_plan_meal_keyboard(
                meal_view.weekly_plan_id,
                meal_view.meal_date,
                [
                    (item.planned_meal_item_id, f"{item.position + 1}. {item.name}")
                    for item in meal_view.items
                ],
            ),
        )

    @router.callback_query(F.data.startswith("pi:"))
    async def handle_plan_item_callback(callback: CallbackQuery) -> None:
        callback_data = cast(str, callback.data)
        planned_meal_item_id = parse_plan_item_callback(callback_data)
        if planned_meal_item_id is None:
            await callback.answer("Не получилось открыть блюдо.", show_alert=True)
            return

        try:
            item_view = await browsing_service.get_item_view(
                _require_telegram_user_id_from_callback(callback),
                planned_meal_item_id,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _edit_callback_message(
            callback,
            text=_render_item_view(item_view),
            reply_markup=build_plan_item_keyboard(
                item_view.weekly_plan_id,
                item_view.meal_date,
                item_view.planned_meal_id,
            ),
        )

    return router


async def _edit_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer("Сообщение для обновления не найдено.", show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()


def _render_day_view(day_view: StoredPlanDayView) -> str:
    lines = [f"{_format_date(day_view.meal_date)}"]
    if not day_view.meals:
        lines.extend(["", "На этот день блюда пока не сохранены."])
        return "\n".join(lines)

    for meal in day_view.meals:
        item_names = ", ".join(meal.item_names) if meal.item_names else "Пока без блюд"
        lines.extend(
            [
                "",
                f"{_render_slot_name(meal.slot)}: {item_names}",
            ],
        )
        if meal.note:
            lines.append(f"Заметка: {meal.note}")
    lines.append("")
    lines.append("Выбери прием пищи, чтобы спуститься к блюдам.")
    return "\n".join(lines)


def _render_meal_view(meal_view: StoredPlanMealView) -> str:
    lines = [
        f"{_format_date(meal_view.meal_date)}",
        f"{_render_slot_name(meal_view.slot)}",
    ]
    if meal_view.note:
        lines.extend(["", f"Заметка: {meal_view.note}"])

    for item in meal_view.items:
        lines.extend(["", f"{item.position + 1}. {item.name}"])
    lines.append("")
    lines.append("Выбери блюдо, чтобы открыть его карточку.")
    return "\n".join(lines)


def _render_item_view(item_view: StoredPlanItemView) -> str:
    lines = [
        item_view.name,
        f"{_format_date(item_view.meal_date)} · {_render_slot_name(item_view.slot)}",
    ]
    if item_view.summary:
        lines.extend(["", item_view.summary])

    if item_view.adaptation_notes:
        lines.extend(["", "Адаптации:"])
        lines.extend([f"• {note}" for note in item_view.adaptation_notes])

    ingredients = item_view.snapshot_payload.get("ingredients")
    if isinstance(ingredients, list) and ingredients:
        lines.extend(["", "Ингредиенты:"])
        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                lines.append(f"• {ingredient.get('name', 'Без названия')}")

    recipe_sections = [
        ("Подготовка", item_view.snapshot_payload.get("preparation_steps")),
        ("Готовка", item_view.snapshot_payload.get("cooking_steps")),
        ("Подача", item_view.snapshot_payload.get("serving_steps")),
    ]
    for section_title, section_steps in recipe_sections:
        if isinstance(section_steps, list) and section_steps:
            lines.extend(["", f"{section_title}:"])
            for index, step in enumerate(section_steps, start=1):
                if isinstance(step, str) and step.strip():
                    lines.append(f"{index}. {step.strip()}")

    if len(lines) <= 4:
        lines.extend(["", "Подробный рецепт для этого блюда пока не сохранен."])
    return "\n".join(lines)


def _render_meal_button_label(slot: str, item_names: list[str]) -> str:
    if not item_names:
        return _render_slot_name(slot)
    return f"{_render_slot_name(slot)}: {', '.join(item_names)}"


def _render_slot_name(slot: str) -> str:
    slot_labels = {
        "breakfast": "Завтрак",
        "lunch": "Обед",
        "dinner": "Ужин",
        "snack_1": "Перекус 1",
        "snack_2": "Перекус 2",
        "dessert": "Десерт",
    }
    return slot_labels.get(slot, slot)


def _format_date(value: date) -> str:
    weekdays = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return f"{value.strftime('%d.%m.%Y')}, {weekdays[value.weekday()]}"


def _require_telegram_user_id_from_message(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram user context is required")
    return message.from_user.id


def _require_telegram_user_id_from_callback(callback: CallbackQuery) -> int:
    if callback.from_user is None:
        raise ValueError("Telegram user context is required")
    return callback.from_user.id
