# ruff: noqa: RUF001
from __future__ import annotations

from datetime import date
from typing import Any, cast
from uuid import UUID

from aiogram import F, Router
from aiogram.client.bot import Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.analytics import AnalyticsTracker
from aimealplanner.application.planning import (
    RecipeDayContext,
    RecipeItemResult,
    RecipeService,
    RecipeStartContext,
)
from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.db.enums import WeeklyPlanStatus
from aimealplanner.infrastructure.db.repositories import build_planning_repositories
from aimealplanner.infrastructure.recipes import SpoonacularRecipeHintProvider
from aimealplanner.presentation.telegram.analytics import (
    track_callback_event,
    track_command,
    track_message_event,
)
from aimealplanner.presentation.telegram.keyboards.onboarding import (
    CANCEL_LABEL,
    remove_keyboard,
)
from aimealplanner.presentation.telegram.keyboards.recipe import (
    build_recipe_days_keyboard,
    build_recipe_feedback_keyboard,
    build_recipe_item_keyboard,
    build_recipe_items_keyboard,
    parse_recipe_day_callback,
    parse_recipe_feedback_callback,
    parse_recipe_item_callback,
    parse_recipe_week_callback,
)
from aimealplanner.presentation.telegram.states.recipe import RecipeStates

_RECIPE_MODE = "recipe"
_INGREDIENTS_MODE = "ingredients"


def build_recipe_router(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
    recipe_hint_provider: SpoonacularRecipeHintProvider | None,
    analytics: AnalyticsTracker,
) -> Router:
    router = Router(name="recipe")
    recipe_service = RecipeService(
        session_factory,
        build_planning_repositories,
        recipe_client=weekly_plan_generator,
        recipe_hint_provider=recipe_hint_provider,
    )

    @router.message(Command("recipe"))
    async def handle_recipe_command(message: Message) -> None:
        track_command(analytics, message=message, command="recipe")
        await _handle_recipe_start_message(
            message,
            recipe_service=recipe_service,
            mode=_RECIPE_MODE,
        )

    @router.message(Command("ingredients"))
    async def handle_ingredients_command(message: Message) -> None:
        track_command(analytics, message=message, command="ingredients")
        await _handle_recipe_start_message(
            message,
            recipe_service=recipe_service,
            mode=_INGREDIENTS_MODE,
        )

    @router.callback_query(F.data.startswith("rpw:"))
    async def handle_recipe_week_callback(callback: CallbackQuery) -> None:
        parsed_value = parse_recipe_week_callback(cast(str, callback.data))
        if parsed_value is None:
            await callback.answer("Не получилось открыть неделю.", show_alert=True)
            return

        mode, weekly_plan_id = parsed_value
        if not _is_supported_mode(mode):
            await callback.answer("Неизвестный режим просмотра.", show_alert=True)
            return

        try:
            context = await recipe_service.get_start_context(
                _require_telegram_user_id_from_callback(callback),
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        if context.weekly_plan_id != weekly_plan_id:
            await callback.answer("Открываю актуальную неделю.")
            await _edit_callback_message(
                callback,
                text=_render_recipe_start(context, mode=mode),
                reply_markup=_build_days_keyboard(context, mode=mode),
                answer_callback=False,
            )
            return

        await _edit_callback_message(
            callback,
            text=_render_recipe_start(context, mode=mode),
            reply_markup=_build_days_keyboard(context, mode=mode),
        )

    @router.callback_query(F.data.startswith("rpd:"))
    async def handle_recipe_day_callback(callback: CallbackQuery) -> None:
        parsed_value = parse_recipe_day_callback(cast(str, callback.data))
        if parsed_value is None:
            await callback.answer("Не получилось открыть выбранный день.", show_alert=True)
            return

        mode, weekly_plan_id, meal_date = parsed_value
        if not _is_supported_mode(mode):
            await callback.answer("Неизвестный режим просмотра.", show_alert=True)
            return

        try:
            day_context = await recipe_service.get_day_context(
                _require_telegram_user_id_from_callback(callback),
                weekly_plan_id=weekly_plan_id,
                meal_date=meal_date,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _edit_callback_message(
            callback,
            text=_render_recipe_day(day_context, mode=mode),
            reply_markup=build_recipe_items_keyboard(
                mode=mode,
                weekly_plan_id=weekly_plan_id,
                items=[
                    (
                        item.planned_meal_item_id,
                        f"{_render_slot_name(item.slot)} · {item.dish_name}",
                    )
                    for item in day_context.items
                ],
            ),
        )

    @router.callback_query(F.data.startswith("rpi:"))
    async def handle_recipe_item_callback(callback: CallbackQuery) -> None:
        parsed_value = parse_recipe_item_callback(cast(str, callback.data))
        if parsed_value is None:
            await callback.answer("Не получилось открыть выбранное блюдо.", show_alert=True)
            return

        mode, planned_meal_item_id = parsed_value
        if not _is_supported_mode(mode):
            await callback.answer("Неизвестный режим просмотра.", show_alert=True)
            return

        await callback.answer("Открываю блюдо...")
        try:
            async with ChatActionSender.typing(
                bot=_require_callback_bot(callback),
                chat_id=_require_callback_message(callback).chat.id,
            ):
                item_result = await recipe_service.get_item_with_recipe(
                    _require_telegram_user_id_from_callback(callback),
                    planned_meal_item_id,
                )
        except ValueError as err:
            await _require_callback_message(callback).answer(
                str(err),
                reply_markup=remove_keyboard(),
            )
            return

        await _edit_callback_message(
            callback,
            text=_render_recipe_item(item_result, mode=mode),
            reply_markup=build_recipe_item_keyboard(
                mode=mode,
                weekly_plan_id=item_result.item_view.weekly_plan_id,
                meal_date=item_result.item_view.meal_date,
                planned_meal_item_id=item_result.item_view.planned_meal_item_id,
            ),
            answer_callback=False,
        )
        track_callback_event(
            analytics,
            callback=callback,
            event="recipe_viewed" if mode == _RECIPE_MODE else "ingredients_viewed",
            properties={"slot": item_result.item_view.slot},
        )

    @router.callback_query(F.data.startswith("rpf:"))
    async def handle_recipe_feedback_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed_value = parse_recipe_feedback_callback(cast(str, callback.data))
        if parsed_value is None:
            await callback.answer("Не получилось открыть корректировку рецепта.", show_alert=True)
            return

        action, planned_meal_item_id = parsed_value
        if action == "cancel":
            await _cancel_recipe_feedback(
                callback=callback,
                state=state,
                recipe_service=recipe_service,
            )
            return
        if action != "start":
            await callback.answer("Неизвестное действие.", show_alert=True)
            return

        try:
            item_result = await recipe_service.get_item_with_recipe(
                _require_telegram_user_id_from_callback(callback),
                planned_meal_item_id,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        message = _require_callback_message(callback)
        await state.set_state(RecipeStates.feedback)
        await state.update_data(
            recipe_feedback_item_id=planned_meal_item_id.hex,
            recipe_feedback_message_id=message.message_id,
            recipe_feedback_chat_id=message.chat.id,
        )
        await _edit_callback_message(
            callback,
            text=_render_recipe_feedback_prompt(item_result.item_view),
            reply_markup=build_recipe_feedback_keyboard(
                planned_meal_item_id=planned_meal_item_id,
            ),
        )

    @router.message(RecipeStates.feedback)
    async def handle_recipe_feedback_message(
        message: Message,
        state: FSMContext,
    ) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши, что поправить в рецепте, обычным текстом.")
            return

        if raw_text in {"/cancel", CANCEL_LABEL}:
            await _cancel_recipe_feedback_from_message(
                message=message,
                state=state,
                recipe_service=recipe_service,
            )
            return

        state_data = await state.get_data()
        planned_meal_item_id = _get_recipe_feedback_item_id(state_data)
        if planned_meal_item_id is None:
            await state.clear()
            await message.answer("Не удалось восстановить рецепт. Открой /recipe заново.")
            return

        async with ChatActionSender.typing(
            bot=_require_message_bot(message),
            chat_id=message.chat.id,
        ):
            try:
                item_result = await recipe_service.adjust_item_recipe(
                    _require_telegram_user_id_from_message(message),
                    planned_meal_item_id,
                    raw_text,
                )
            except ValueError as err:
                await message.answer(str(err), reply_markup=remove_keyboard())
                return

        await state.clear()
        await _edit_recipe_message(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_recipe_item(item_result, mode=_RECIPE_MODE),
            reply_markup=build_recipe_item_keyboard(
                mode=_RECIPE_MODE,
                weekly_plan_id=item_result.item_view.weekly_plan_id,
                meal_date=item_result.item_view.meal_date,
                planned_meal_item_id=item_result.item_view.planned_meal_item_id,
            ),
        )
        track_message_event(
            analytics,
            message=message,
            event="recipe_adjusted",
            properties={"slot": item_result.item_view.slot},
        )

    return router


async def _handle_recipe_start_message(
    message: Message,
    *,
    recipe_service: RecipeService,
    mode: str,
) -> None:
    try:
        context = await recipe_service.get_start_context(
            _require_telegram_user_id_from_message(message),
        )
    except ValueError as err:
        await message.answer(str(err), reply_markup=remove_keyboard())
        return

    await message.answer(
        _render_recipe_start(context, mode=mode),
        reply_markup=_build_days_keyboard(context, mode=mode),
    )


def _build_days_keyboard(
    context: RecipeStartContext,
    *,
    mode: str,
) -> InlineKeyboardMarkup:
    return build_recipe_days_keyboard(
        mode=mode,
        weekly_plan_id=context.weekly_plan_id,
        days=[
            (
                day.meal_date,
                (
                    f"{day.meal_date.strftime('%d.%m.%Y')} "
                    f"({_weekday_name(day.meal_date)}) · "
                    f"{day.items_count} {_render_item_count_label(day.items_count)}"
                ),
            )
            for day in context.days
        ],
    )


def _render_recipe_start(context: RecipeStartContext, *, mode: str) -> str:
    title = "Рецепты текущей недели." if mode == _RECIPE_MODE else "Ингредиенты текущей недели."
    action = (
        "Выбери день, чтобы открыть рецепт блюда."
        if mode == _RECIPE_MODE
        else "Выбери день, чтобы посмотреть ингредиенты по блюду."
    )
    plan_type = (
        "Сейчас открыт подтвержденный план."
        if context.status is WeeklyPlanStatus.CONFIRMED
        else "Сейчас открыт черновик недели."
    )
    return (
        f"{title}\n"
        f"Период: {context.start_date.strftime('%d.%m.%Y')} - "
        f"{context.end_date.strftime('%d.%m.%Y')}.\n"
        f"{plan_type}\n\n"
        f"{action}"
    )


def _render_recipe_day(day_context: RecipeDayContext, *, mode: str) -> str:
    title = (
        f"Рецепты · {day_context.meal_date.strftime('%d.%m.%Y')} "
        f"({_weekday_name(day_context.meal_date)})"
        if mode == _RECIPE_MODE
        else (
            f"Ингредиенты · {day_context.meal_date.strftime('%d.%m.%Y')} "
            f"({_weekday_name(day_context.meal_date)})"
        )
    )
    lines = [title, "", "Блюда на день:"]
    for index, item in enumerate(day_context.items, start=1):
        lines.append(f"{index}. {_render_slot_name(item.slot)} · {item.dish_name}")
    lines.extend(
        [
            "",
            (
                "Выбери блюдо, чтобы открыть рецепт."
                if mode == _RECIPE_MODE
                else "Выбери блюдо, чтобы увидеть только ингредиенты."
            ),
        ],
    )
    return "\n".join(lines)


def _render_recipe_item(item_result: RecipeItemResult, *, mode: str) -> str:
    item_view = item_result.item_view
    if mode == _INGREDIENTS_MODE:
        return _render_ingredients_text(item_view)
    return _render_recipe_text(item_view)


def _render_recipe_text(item_view: StoredPlanItemView) -> str:
    payload = item_view.snapshot_payload
    lines = [
        f"Рецепт · {item_view.name}",
        "",
        (
            f"Когда: {item_view.meal_date.strftime('%d.%m.%Y')} "
            f"({_weekday_name(item_view.meal_date)}) · {_render_slot_name(item_view.slot)}"
        ),
    ]
    if item_view.summary:
        lines.append(f"Кратко: {item_view.summary}")
    if item_view.adaptation_notes:
        lines.extend(
            [
                "",
                "Учесть для семьи:",
                *[f"- {note}" for note in item_view.adaptation_notes],
            ],
        )

    time_lines = _render_time_lines(payload)
    if time_lines:
        lines.extend(["", "Время:"])
        lines.extend(time_lines)

    ingredients = _render_ingredient_lines(payload)
    if ingredients:
        lines.extend(["", "Ингредиенты:"])
        lines.extend(ingredients)

    preparation_steps = _render_steps(payload, "preparation_steps")
    if preparation_steps:
        lines.extend(["", "Подготовка:"])
        lines.extend(preparation_steps)

    cooking_steps = _render_steps(payload, "cooking_steps")
    if cooking_steps:
        lines.extend(["", "Готовим:"])
        lines.extend(cooking_steps)

    serving_steps = _render_steps(payload, "serving_steps")
    if serving_steps:
        lines.extend(["", "Подача:"])
        lines.extend(serving_steps)

    serving_notes = payload.get("serving_notes")
    if isinstance(serving_notes, str) and serving_notes.strip():
        lines.extend(["", f"Подача и советы: {serving_notes.strip()}"])

    return "\n".join(lines)


def _render_ingredients_text(item_view: StoredPlanItemView) -> str:
    payload = item_view.snapshot_payload
    lines = [
        f"Ингредиенты · {item_view.name}",
        "",
        (
            f"Когда: {item_view.meal_date.strftime('%d.%m.%Y')} "
            f"({_weekday_name(item_view.meal_date)}) · {_render_slot_name(item_view.slot)}"
        ),
    ]
    if item_view.adaptation_notes:
        lines.extend(
            [
                "",
                "Учесть для семьи:",
                *[f"- {note}" for note in item_view.adaptation_notes],
            ],
        )

    ingredient_lines = _render_ingredient_lines(payload)
    if not ingredient_lines:
        lines.extend(["", "Список ингредиентов пока не готов."])
        return "\n".join(lines)

    lines.extend(["", "Нужно:"])
    lines.extend(ingredient_lines)
    return "\n".join(lines)


def _render_ingredient_lines(payload: dict[str, object]) -> list[str]:
    raw_ingredients = payload.get("ingredients")
    if not isinstance(raw_ingredients, list):
        return []

    lines: list[str] = []
    for raw_ingredient in raw_ingredients:
        if not isinstance(raw_ingredient, dict):
            continue
        ingredient_payload = cast(dict[str, object], raw_ingredient)
        name = ingredient_payload.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        amount = ingredient_payload.get("amount")
        preparation_note = ingredient_payload.get("preparation_note")
        line = f"- {name.strip()}"
        if isinstance(amount, str) and amount.strip():
            line += f" — {amount.strip()}"
        if isinstance(preparation_note, str) and preparation_note.strip():
            line += f" ({preparation_note.strip()})"
        lines.append(line)
    return lines


def _render_steps(payload: dict[str, object], field_name: str) -> list[str]:
    raw_steps = payload.get(field_name)
    if not isinstance(raw_steps, list):
        return []
    steps = [step.strip() for step in raw_steps if isinstance(step, str) and step.strip()]
    return [f"{index}. {step}" for index, step in enumerate(steps, start=1)]


def _render_time_lines(payload: dict[str, object]) -> list[str]:
    lines: list[str] = []
    prep_time = payload.get("prep_time_minutes")
    cook_time = payload.get("cook_time_minutes")
    if isinstance(prep_time, int) and prep_time > 0:
        lines.append(f"- Подготовка: {prep_time} мин")
    if isinstance(cook_time, int) and cook_time > 0:
        lines.append(f"- Готовка: {cook_time} мин")
    return lines


async def _edit_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    answer_callback: bool = True,
) -> None:
    message = _require_callback_message(callback)
    await message.edit_text(text, reply_markup=reply_markup)
    if answer_callback:
        await callback.answer()


async def _edit_recipe_message(
    *,
    bot: Bot,
    state_data: dict[str, Any],
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    message_id = cast(int | None, state_data.get("recipe_feedback_message_id"))
    chat_id = cast(int | None, state_data.get("recipe_feedback_chat_id"))
    if message_id is None or chat_id is None:
        return
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )


async def _cancel_recipe_feedback(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    recipe_service: RecipeService,
) -> None:
    state_data = await state.get_data()
    planned_meal_item_id = _get_recipe_feedback_item_id(state_data)
    await state.clear()
    if planned_meal_item_id is None:
        await callback.answer("Сценарий корректировки уже завершен.", show_alert=True)
        return

    try:
        item_result = await recipe_service.get_item_with_recipe(
            _require_telegram_user_id_from_callback(callback),
            planned_meal_item_id,
        )
    except ValueError as err:
        await callback.answer(str(err), show_alert=True)
        return

    await _edit_callback_message(
        callback,
        text=_render_recipe_item(item_result, mode=_RECIPE_MODE),
        reply_markup=build_recipe_item_keyboard(
            mode=_RECIPE_MODE,
            weekly_plan_id=item_result.item_view.weekly_plan_id,
            meal_date=item_result.item_view.meal_date,
            planned_meal_item_id=item_result.item_view.planned_meal_item_id,
        ),
    )


async def _cancel_recipe_feedback_from_message(
    *,
    message: Message,
    state: FSMContext,
    recipe_service: RecipeService,
) -> None:
    state_data = await state.get_data()
    planned_meal_item_id = _get_recipe_feedback_item_id(state_data)
    await state.clear()
    if planned_meal_item_id is None:
        await message.answer("Сценарий корректировки уже завершен.")
        return

    try:
        item_result = await recipe_service.get_item_with_recipe(
            _require_telegram_user_id_from_message(message),
            planned_meal_item_id,
        )
    except ValueError as err:
        await message.answer(str(err), reply_markup=remove_keyboard())
        return

    await _edit_recipe_message(
        bot=_require_message_bot(message),
        state_data=state_data,
        text=_render_recipe_item(item_result, mode=_RECIPE_MODE),
        reply_markup=build_recipe_item_keyboard(
            mode=_RECIPE_MODE,
            weekly_plan_id=item_result.item_view.weekly_plan_id,
            meal_date=item_result.item_view.meal_date,
            planned_meal_item_id=item_result.item_view.planned_meal_item_id,
        ),
    )


def _get_recipe_feedback_item_id(state_data: dict[str, Any]) -> UUID | None:
    raw_value = cast(str | None, state_data.get("recipe_feedback_item_id"))
    if raw_value is None:
        return None
    try:
        return UUID(hex=raw_value)
    except ValueError:
        return None


def _render_recipe_feedback_prompt(item_view: StoredPlanItemView) -> str:
    return (
        f"Что поправить в рецепте «{item_view.name}»?\n\n"
        "Например: слишком много жидкости, не хватает шага с маринадом,\n"
        "нелогичный порядок действий, слишком мало ингредиентов.\n\n"
        "Напиши замечание текстом или нажми «Отмена»."
    )


def _render_item_count_label(count: int) -> str:
    remainder_ten = count % 10
    remainder_hundred = count % 100
    if remainder_ten == 1 and remainder_hundred != 11:
        return "блюдо"
    if remainder_ten in {2, 3, 4} and remainder_hundred not in {12, 13, 14}:
        return "блюда"
    return "блюд"


def _weekday_name(value: date) -> str:
    weekdays = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return weekdays[value.weekday()]


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


def _is_supported_mode(value: str) -> bool:
    return value in {_RECIPE_MODE, _INGREDIENTS_MODE}


def _require_callback_message(callback: CallbackQuery) -> Message:
    message = callback.message
    if not isinstance(message, Message):
        raise ValueError("Callback message is unavailable")
    return message


def _require_telegram_user_id_from_message(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram user is unavailable")
    return message.from_user.id


def _require_telegram_user_id_from_callback(callback: CallbackQuery) -> int:
    if callback.from_user is None:
        raise ValueError("Telegram user is unavailable")
    return callback.from_user.id


def _require_text(message: Message) -> str:
    if not isinstance(message.text, str) or not message.text.strip():
        raise ValueError("Message text is unavailable")
    return message.text.strip()


def _require_message_bot(message: Message) -> Bot:
    if message.bot is None:
        raise ValueError("Telegram bot is unavailable")
    return message.bot


def _require_callback_bot(callback: CallbackQuery) -> Bot:
    if callback.bot is None:
        raise ValueError("Telegram bot is unavailable")
    return callback.bot
