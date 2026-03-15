# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import cast
from uuid import UUID

from aiogram import F, Router
from aiogram.client.bot import Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning import (
    DishPolicyService,
    DishReplacementService,
    PlannedMealItemReplacement,
    PlanningBrowsingService,
    ReplacementCandidate,
)
from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDayView,
    StoredPlanItemView,
    StoredPlanMealView,
)
from aimealplanner.application.planning.generation_dto import DishQuickAction
from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict
from aimealplanner.infrastructure.db.repositories import build_planning_repositories
from aimealplanner.infrastructure.recipes import SpoonacularRecipeHintProvider
from aimealplanner.presentation.telegram.keyboards.onboarding import CANCEL_LABEL, remove_keyboard
from aimealplanner.presentation.telegram.keyboards.planning import (
    REJECT_DISH_REASON_LABEL,
    build_plan_day_keyboard,
    build_plan_days_keyboard,
    build_plan_item_keyboard,
    build_plan_meal_keyboard,
    build_reject_action_keyboard,
    build_reject_reason_keyboard,
    build_replacement_candidates_keyboard,
    parse_plan_custom_edit_callback,
    parse_plan_day_callback,
    parse_plan_item_callback,
    parse_plan_meal_callback,
    parse_plan_policy_callback,
    parse_plan_reject_flow_callback,
    parse_plan_replace_callback,
    parse_plan_replace_choose_callback,
    parse_plan_suggested_action_callback,
    parse_plan_week_callback,
)
from aimealplanner.presentation.telegram.states.plan_browser import PlanBrowserStates


def build_plan_browser_router(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
    recipe_hint_provider: SpoonacularRecipeHintProvider | None,
) -> Router:
    router = Router(name="plan_browser")
    browsing_service = PlanningBrowsingService(session_factory, build_planning_repositories)
    policy_service = DishPolicyService(
        session_factory,
        build_planning_repositories,
        reason_client=weekly_plan_generator,
    )
    replacement_service = DishReplacementService(
        session_factory,
        build_planning_repositories,
        suggestion_client=weekly_plan_generator,
        recipe_hint_provider=recipe_hint_provider,
    )

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
            reply_markup=_build_item_keyboard(item_view),
        )

    @router.callback_query(F.data.startswith("pr:"))
    async def handle_plan_replace_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        callback_data = cast(str, callback.data)
        planned_meal_item_id = parse_plan_replace_callback(callback_data)
        if planned_meal_item_id is None:
            await callback.answer("Не получилось подобрать замену.", show_alert=True)
            return

        message = _require_callback_message(callback)
        await callback.answer("Подбираю варианты замены...")
        async with ChatActionSender.typing(
            bot=_require_callback_bot(callback),
            chat_id=message.chat.id,
        ):
            try:
                suggestion_result = await replacement_service.suggest_replacements(
                    _require_telegram_user_id_from_callback(callback),
                    planned_meal_item_id,
                )
            except ValueError as err:
                await message.answer(str(err))
                return

        await _store_replacement_candidates(
            state,
            planned_meal_item_id=planned_meal_item_id,
            candidates=suggestion_result.candidates,
        )
        await _edit_callback_message(
            callback,
            text=_render_replacement_candidates(
                suggestion_result.item_view,
                suggestion_result.candidates,
            ),
            reply_markup=build_replacement_candidates_keyboard(
                planned_meal_item_id=planned_meal_item_id,
                weekly_plan_id=suggestion_result.item_view.weekly_plan_id,
                meal_date=suggestion_result.item_view.meal_date,
                planned_meal_id=suggestion_result.item_view.planned_meal_id,
                candidates=[
                    (index, candidate.name)
                    for index, candidate in enumerate(suggestion_result.candidates)
                ],
            ),
            answer_callback=False,
        )

    @router.callback_query(F.data.startswith("ps:"))
    async def handle_plan_suggested_action_callback(callback: CallbackQuery) -> None:
        callback_data = cast(str, callback.data)
        parsed_value = parse_plan_suggested_action_callback(callback_data)
        if parsed_value is None:
            await callback.answer("Не получилось изменить блюдо.", show_alert=True)
            return

        planned_meal_item_id, action_index = parsed_value
        try:
            item_view = await browsing_service.get_item_view(
                _require_telegram_user_id_from_callback(callback),
                planned_meal_item_id,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        if action_index < 0 or action_index >= len(item_view.suggested_actions):
            await callback.answer("Подсказка для этого блюда устарела.", show_alert=True)
            return

        instruction = item_view.suggested_actions[action_index].instruction
        message = _require_callback_message(callback)
        await callback.answer("Корректирую блюдо...")
        async with ChatActionSender.typing(
            bot=_require_callback_bot(callback),
            chat_id=message.chat.id,
        ):
            try:
                apply_result = await replacement_service.apply_adjustment(
                    _require_telegram_user_id_from_callback(callback),
                    planned_meal_item_id,
                    instruction,
                    generation_source="ai_adjustment:suggested",
                )
            except ValueError as err:
                await message.answer(str(err))
                return

        await _edit_callback_message(
            callback,
            text=_render_item_view(apply_result.updated_item),
            reply_markup=_build_item_keyboard(apply_result.updated_item),
            answer_callback=False,
        )

    @router.callback_query(F.data.startswith("pe:"))
    async def handle_plan_custom_edit_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        callback_data = cast(str, callback.data)
        planned_meal_item_id = parse_plan_custom_edit_callback(callback_data)
        if planned_meal_item_id is None:
            await callback.answer("Не получилось открыть редактирование.", show_alert=True)
            return

        message = _require_callback_message(callback)
        await state.set_state(PlanBrowserStates.custom_item_adjustment)
        await state.update_data(
            custom_adjustment_item_id=planned_meal_item_id.hex,
            custom_adjustment_message_id=message.message_id,
            custom_adjustment_chat_id=message.chat.id,
        )
        await callback.answer()
        await message.answer(
            (
                "Напиши, как изменить это блюдо.\n"
                "Например: сделать менее острым, добавить больше пармезана,\n"
                "подобрать вариант без сахара.\n"
                "Чтобы отменить, отправь /cancel."
            ),
            reply_markup=remove_keyboard(),
        )

    @router.callback_query(F.data.startswith("pp:"))
    async def handle_plan_policy_callback(callback: CallbackQuery) -> None:
        callback_data = cast(str, callback.data)
        parsed_value = parse_plan_policy_callback(callback_data)
        if parsed_value is None:
            await callback.answer("Не получилось сохранить правило для блюда.", show_alert=True)
            return

        planned_meal_item_id, verdict_value = parsed_value
        verdict = _parse_policy_verdict(verdict_value)
        if verdict is None:
            await callback.answer("Такое правило пока не поддерживается.", show_alert=True)
            return

        try:
            update_result = await policy_service.set_household_policy(
                _require_telegram_user_id_from_callback(callback),
                planned_meal_item_id,
                verdict=verdict,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _edit_callback_message(
            callback,
            text=_render_item_view(update_result.updated_item),
            reply_markup=_build_item_keyboard(update_result.updated_item),
            answer_callback=False,
        )
        await callback.answer(_render_policy_toast(verdict))

    @router.callback_query(F.data.startswith("pn:"))
    async def handle_plan_reject_flow_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        callback_data = cast(str, callback.data)
        parsed_value = parse_plan_reject_flow_callback(callback_data)
        if parsed_value is None:
            await callback.answer("Не получилось обработать это действие.", show_alert=True)
            return

        planned_meal_item_id, action = parsed_value
        if action == "ask":
            await _edit_callback_message(
                callback,
                text="Что сделать с этим блюдом в текущем плане?",
                reply_markup=build_reject_action_keyboard(planned_meal_item_id),
            )
            return

        if action not in {"remove", "replace"}:
            await callback.answer("Такое действие пока не поддерживается.", show_alert=True)
            return

        message = _require_callback_message(callback)
        await state.set_state(PlanBrowserStates.reject_reason)
        await state.update_data(
            reject_item_id=planned_meal_item_id.hex,
            reject_action=action,
            reject_message_id=message.message_id,
            reject_chat_id=message.chat.id,
        )
        await callback.answer()
        await message.answer(
            (
                "Почему больше не предлагать это блюдо?\n"
                "Напиши коротко. Если причина только в самом блюде, так и напиши.\n"
                "Чтобы отменить, отправь /cancel."
            ),
            reply_markup=build_reject_reason_keyboard(),
        )

    @router.message(PlanBrowserStates.custom_item_adjustment)
    async def handle_custom_item_adjustment(message: Message, state: FSMContext) -> None:
        try:
            instruction = _require_text(message)
        except ValueError:
            await message.answer("Напиши правку обычным текстом или отправь /cancel.")
            return
        if instruction == "/cancel" or instruction == CANCEL_LABEL:
            await state.clear()
            await message.answer(
                "Ок, оставляю блюдо без изменений.",
                reply_markup=remove_keyboard(),
            )
            return

        state_data = await state.get_data()
        planned_meal_item_hex = cast(str | None, state_data.get("custom_adjustment_item_id"))
        if planned_meal_item_hex is None:
            await state.clear()
            await message.answer(
                "Не удалось восстановить контекст редактирования. Открой блюдо заново через /week.",
                reply_markup=remove_keyboard(),
            )
            return

        planned_meal_item_id = UUID(hex=planned_meal_item_hex)
        async with ChatActionSender.typing(
            bot=_require_message_bot(message),
            chat_id=message.chat.id,
        ):
            try:
                apply_result = await replacement_service.apply_adjustment(
                    _require_telegram_user_id_from_message(message),
                    planned_meal_item_id,
                    instruction,
                    generation_source="ai_adjustment:custom",
                )
            except ValueError as err:
                await message.answer(str(err))
                return

        await state.clear()
        await _edit_stored_item_message(
            message,
            state_data,
            apply_result.updated_item,
        )
        await message.answer(
            "Готово, карточку блюда обновил.",
            reply_markup=remove_keyboard(),
        )

    @router.message(PlanBrowserStates.reject_reason)
    async def handle_reject_reason(message: Message, state: FSMContext) -> None:
        try:
            raw_reason = _require_text(message)
        except ValueError:
            await message.answer("Напиши причину обычным текстом или отправь /cancel.")
            return
        if raw_reason == "/cancel" or raw_reason == CANCEL_LABEL:
            await state.clear()
            await message.answer(
                "Ок, оставляю блюдо как есть.",
                reply_markup=remove_keyboard(),
            )
            return
        if raw_reason == REJECT_DISH_REASON_LABEL:
            raw_reason = "Не подходит именно это блюдо, без новых ограничений для семьи."

        state_data = await state.get_data()
        planned_meal_item_hex = cast(str | None, state_data.get("reject_item_id"))
        reject_action = cast(str | None, state_data.get("reject_action"))
        if planned_meal_item_hex is None or reject_action is None:
            await state.clear()
            await message.answer(
                "Не удалось восстановить контекст. Открой блюдо заново через /week.",
                reply_markup=remove_keyboard(),
            )
            return

        planned_meal_item_id = UUID(hex=planned_meal_item_hex)
        async with ChatActionSender.typing(
            bot=_require_message_bot(message),
            chat_id=message.chat.id,
        ):
            try:
                policy_result = await policy_service.set_household_policy(
                    _require_telegram_user_id_from_message(message),
                    planned_meal_item_id,
                    verdict=DishFeedbackVerdict.NEVER_AGAIN,
                    raw_reason=raw_reason,
                )
            except ValueError as err:
                await message.answer(str(err))
                return

        if reject_action == "remove":
            removal_result = await policy_service.remove_item_from_current_plan(
                _require_telegram_user_id_from_message(message),
                planned_meal_item_id,
            )
            await state.clear()
            updated_meal = await browsing_service.get_meal_view(
                _require_telegram_user_id_from_message(message),
                removal_result.updated_meal_id,
            )
            await _edit_stored_meal_message(
                message,
                state_data,
                updated_meal,
            )
            await message.answer(
                "Блюдо убрал и больше не буду предлагать его семье.",
                reply_markup=remove_keyboard(),
            )
            return

        await state.clear()
        suggestion_result = await replacement_service.suggest_replacements(
            _require_telegram_user_id_from_message(message),
            planned_meal_item_id,
        )
        await _store_replacement_candidates(
            state,
            planned_meal_item_id=planned_meal_item_id,
            candidates=suggestion_result.candidates,
        )
        await _edit_stored_item_message(
            message,
            state_data,
            policy_result.updated_item,
            text_override=_render_replacement_candidates(
                suggestion_result.item_view,
                suggestion_result.candidates,
            ),
            reply_markup_override=build_replacement_candidates_keyboard(
                planned_meal_item_id=planned_meal_item_id,
                weekly_plan_id=suggestion_result.item_view.weekly_plan_id,
                meal_date=suggestion_result.item_view.meal_date,
                planned_meal_id=suggestion_result.item_view.planned_meal_id,
                candidates=[
                    (index, candidate.name)
                    for index, candidate in enumerate(suggestion_result.candidates)
                ],
            ),
        )
        await message.answer(
            "Запомнил это блюдо как нежелательное для семьи. Ниже подобрал замену.",
            reply_markup=remove_keyboard(),
        )

    @router.callback_query(F.data.startswith("pc:"))
    async def handle_plan_replace_choose_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        callback_data = cast(str, callback.data)
        parsed_value = parse_plan_replace_choose_callback(callback_data)
        if parsed_value is None:
            await callback.answer("Не получилось применить замену.", show_alert=True)
            return

        planned_meal_item_id, index = parsed_value
        candidate = await _get_replacement_candidate(
            state,
            planned_meal_item_id=planned_meal_item_id,
            index=index,
        )
        if candidate is None:
            await callback.answer("Варианты замены устарели. Подбери их заново.", show_alert=True)
            return

        try:
            apply_result = await replacement_service.apply_replacement(
                _require_telegram_user_id_from_callback(callback),
                PlannedMealItemReplacement(
                    planned_meal_item_id=planned_meal_item_id,
                    name=candidate.name,
                    summary=candidate.summary,
                    adaptation_notes=candidate.adaptation_notes,
                    snapshot_payload={
                        "summary": candidate.summary,
                        "replacement_reason": candidate.reason,
                        "generation_source": "ai_replacement",
                        "suggested_actions": [
                            {
                                "label": action.label,
                                "instruction": action.instruction,
                            }
                            for action in candidate.suggested_actions
                        ],
                    },
                ),
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _clear_replacement_candidates(state, planned_meal_item_id)
        await _edit_callback_message(
            callback,
            text=_render_item_view(apply_result.updated_item),
            reply_markup=_build_item_keyboard(apply_result.updated_item),
        )

    return router


async def _edit_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    answer_callback: bool = True,
) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer("Сообщение для обновления не найдено.", show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=reply_markup)
    if answer_callback:
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


def _render_replacement_candidates(
    item_view: StoredPlanItemView,
    candidates: list[ReplacementCandidate],
) -> str:
    lines = [
        f"Замена для блюда: {item_view.name}",
        f"{_format_date(item_view.meal_date)} · {_render_slot_name(item_view.slot)}",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                "",
                f"{index}. {candidate.name}",
                candidate.summary,
            ],
        )
        if candidate.reason:
            lines.append(f"Почему подходит: {candidate.reason}")
        if candidate.adaptation_notes:
            lines.append(f"Адаптации: {', '.join(candidate.adaptation_notes)}")
    lines.append("")
    lines.append("Выбери вариант кнопкой ниже.")
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

    adjustment_instruction = item_view.snapshot_payload.get("adjustment_instruction")
    if isinstance(adjustment_instruction, str) and adjustment_instruction.strip():
        lines.extend(["", f"Последняя правка: {adjustment_instruction.strip()}"])

    adjustment_reason = item_view.snapshot_payload.get("adjustment_reason")
    if isinstance(adjustment_reason, str) and adjustment_reason.strip():
        lines.append(f"Что изменилось: {adjustment_reason.strip()}")

    if item_view.adaptation_notes:
        lines.extend(["", "Адаптации:"])
        lines.extend([f"• {note}" for note in item_view.adaptation_notes])

    if item_view.household_policy_verdict is not None:
        lines.extend(
            [
                "",
                f"Статус для семьи: {_render_policy_verdict(item_view.household_policy_verdict)}",
            ],
        )
        if item_view.household_policy_note:
            lines.append(f"Заметка: {item_view.household_policy_note}")

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


def _require_text(message: Message) -> str:
    if message.text is None or not message.text.strip():
        raise ValueError("Text message is required")
    return message.text.strip()


def _require_telegram_user_id_from_callback(callback: CallbackQuery) -> int:
    if callback.from_user is None:
        raise ValueError("Telegram user context is required")
    return callback.from_user.id


def _require_callback_message(callback: CallbackQuery) -> Message:
    if callback.message is None or not isinstance(callback.message, Message):
        raise ValueError("Telegram message context is required")
    return callback.message


def _require_message_bot(message: Message) -> Bot:
    if message.bot is None:
        raise ValueError("Telegram bot context is required")
    return message.bot


def _require_callback_bot(callback: CallbackQuery) -> Bot:
    if callback.bot is None:
        raise ValueError("Telegram bot context is required")
    return callback.bot


def _parse_policy_verdict(value: str) -> DishFeedbackVerdict | None:
    try:
        return DishFeedbackVerdict(value)
    except ValueError:
        return None


def _render_policy_toast(verdict: DishFeedbackVerdict) -> str:
    if verdict is DishFeedbackVerdict.FAVORITE:
        return "Сохранил блюдо как любимое для семьи."
    if verdict is DishFeedbackVerdict.NEVER_AGAIN:
        return "Больше не буду предлагать это блюдо семье."
    return "Сохранил правило для блюда."


def _render_policy_verdict(verdict: DishFeedbackVerdict) -> str:
    labels = {
        DishFeedbackVerdict.FAVORITE: "Любимое",
        DishFeedbackVerdict.CAN_REPEAT: "Можно повторять",
        DishFeedbackVerdict.RARELY_REPEAT: "Редко повторять",
        DishFeedbackVerdict.NEVER_AGAIN: "Не предлагать семье",
    }
    return labels.get(verdict, verdict.value)


def _build_item_keyboard(item_view: StoredPlanItemView) -> InlineKeyboardMarkup:
    return build_plan_item_keyboard(
        item_view.weekly_plan_id,
        item_view.meal_date,
        item_view.planned_meal_id,
        item_view.planned_meal_item_id,
        [(index, action.label) for index, action in enumerate(item_view.suggested_actions)],
    )


async def _edit_stored_item_message(
    message: Message,
    state_data: dict[str, object],
    item_view: StoredPlanItemView,
    *,
    text_override: str | None = None,
    reply_markup_override: InlineKeyboardMarkup | None = None,
) -> None:
    chat_id = cast(
        int | str | None,
        state_data.get("custom_adjustment_chat_id") or state_data.get("reject_chat_id"),
    )
    message_id = cast(
        int | None,
        state_data.get("custom_adjustment_message_id") or state_data.get("reject_message_id"),
    )
    text = text_override or _render_item_view(item_view)
    reply_markup = reply_markup_override or _build_item_keyboard(item_view)
    if chat_id is None or message_id is None:
        await message.answer(
            text,
            reply_markup=reply_markup,
        )
        return

    await _require_message_bot(message).edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
    )


async def _edit_stored_meal_message(
    message: Message,
    state_data: dict[str, object],
    meal_view: StoredPlanMealView,
) -> None:
    chat_id = cast(int | str | None, state_data.get("reject_chat_id"))
    message_id = cast(int | None, state_data.get("reject_message_id"))
    text = _render_meal_view(meal_view)
    reply_markup = build_plan_meal_keyboard(
        meal_view.weekly_plan_id,
        meal_view.meal_date,
        [
            (item.planned_meal_item_id, f"{item.position + 1}. {item.name}")
            for item in meal_view.items
        ],
    )
    if chat_id is None or message_id is None:
        await message.answer(text, reply_markup=reply_markup)
        return

    await _require_message_bot(message).edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
    )


async def _store_replacement_candidates(
    state: FSMContext,
    *,
    planned_meal_item_id: UUID,
    candidates: list[ReplacementCandidate],
) -> None:
    state_data = await state.get_data()
    replacement_candidates = cast(
        dict[str, list[dict[str, object]]],
        state_data.get("replacement_candidates", {}),
    )
    replacement_candidates[planned_meal_item_id.hex] = [
        asdict(candidate) for candidate in candidates
    ]
    await state.update_data(replacement_candidates=replacement_candidates)


async def _get_replacement_candidate(
    state: FSMContext,
    *,
    planned_meal_item_id: UUID,
    index: int,
) -> ReplacementCandidate | None:
    state_data = await state.get_data()
    replacement_candidates = cast(
        dict[str, list[dict[str, object]]],
        state_data.get("replacement_candidates", {}),
    )
    candidates_payload = replacement_candidates.get(planned_meal_item_id.hex)
    if candidates_payload is None or index < 0 or index >= len(candidates_payload):
        return None
    candidate_payload = candidates_payload[index]
    return ReplacementCandidate(
        name=cast(str, candidate_payload["name"]),
        summary=cast(str, candidate_payload["summary"]),
        adaptation_notes=cast(list[str], candidate_payload["adaptation_notes"]),
        suggested_actions=[
            DishQuickAction(
                label=cast(str, action_payload["label"]),
                instruction=cast(str, action_payload["instruction"]),
            )
            for action_payload in cast(
                list[dict[str, object]],
                candidate_payload.get("suggested_actions", []),
            )
            if isinstance(action_payload, dict)
        ],
        reason=cast(str | None, candidate_payload.get("reason")),
    )


async def _clear_replacement_candidates(state: FSMContext, planned_meal_item_id: UUID) -> None:
    state_data = await state.get_data()
    replacement_candidates = cast(
        dict[str, list[dict[str, object]]],
        state_data.get("replacement_candidates", {}),
    )
    replacement_candidates.pop(planned_meal_item_id.hex, None)
    await state.update_data(replacement_candidates=replacement_candidates)
