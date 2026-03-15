# ruff: noqa: RUF001
from __future__ import annotations

from datetime import time
from typing import Any, cast
from uuid import UUID

from aiogram import F, Router
from aiogram.client.bot import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.onboarding import PantryItemInput
from aimealplanner.application.settings import (
    FamilySettingsView,
    MemberSettingsView,
    NewSettingsMemberInput,
    PantrySettingsView,
    SettingsHomeView,
    SettingsService,
    StoredSettingsDishPolicy,
    StoredSettingsMember,
    StoredSettingsPantryItem,
    StoredSettingsUser,
)
from aimealplanner.infrastructure.db.enums import (
    DishFeedbackVerdict,
    PantryStockLevel,
    RepeatabilityMode,
)
from aimealplanner.infrastructure.db.repositories import build_settings_repository
from aimealplanner.presentation.telegram.keyboards.onboarding import SKIP_LABEL
from aimealplanner.presentation.telegram.keyboards.settings import (
    CLEAR_LABEL,
    build_family_member_callback,
    build_family_member_keyboard,
    build_member_callback,
    build_member_detail_keyboard,
    build_pantry_item_callback,
    build_pantry_item_keyboard,
    build_pantry_page_callback,
    build_pantry_stock_choice_keyboard,
    build_policy_detail_keyboard,
    build_policy_list_keyboard,
    build_prompt_back_keyboard,
    build_settings_family_keyboard,
    build_settings_home_callback,
    build_settings_home_keyboard,
    build_settings_members_keyboard,
    build_settings_pantry_keyboard,
    build_settings_planning_keyboard,
    build_settings_policy_home_keyboard,
    build_settings_reminders_keyboard,
    build_settings_section_callback,
    build_weekday_keyboard,
    parse_family_callback,
    parse_member_callback,
    parse_pantry_callback,
    parse_planning_callback,
    parse_policy_callback,
    parse_reminder_callback,
    parse_settings_section_callback,
    parse_weekday_callback,
)
from aimealplanner.presentation.telegram.onboarding_parsing import (
    normalize_name,
    parse_quantity_hint,
    parse_time_input,
    split_list_input,
)
from aimealplanner.presentation.telegram.states.settings import SettingsStates

_MESSAGE_ID_KEY = "settings_message_id"
_CHAT_ID_KEY = "settings_chat_id"
_MEMBER_ID_KEY = "settings_member_id"
_PENDING_MEMBER_NAME_KEY = "settings_pending_member_name"
_PENDING_MEMBER_CONSTRAINTS_KEY = "settings_pending_member_constraints"
_PENDING_MEMBER_CUISINES_KEY = "settings_pending_member_cuisines"
_PENDING_WEEKLY_DAY_KEY = "settings_pending_weekly_day"
_PENDING_PANTRY_NAME_KEY = "settings_pending_pantry_name"
_PENDING_PANTRY_STOCK_KEY = "settings_pending_pantry_stock"
_PANTRY_ITEM_ID_KEY = "settings_pantry_item_id"
_PANTRY_PAGE_KEY = "settings_pantry_page"
_WEEKDAY_MODE_KEY = "settings_weekday_mode"
_PANTRY_PAGE_SIZE = 8


def build_settings_router(
    session_factory: async_sessionmaker[AsyncSession],
) -> Router:
    router = Router(name="settings")
    service = SettingsService(session_factory, build_settings_repository)

    @router.message(Command("settings"))
    async def handle_settings_command(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            home_view = await service.get_home(_require_telegram_user_id_from_message(message))
        except ValueError as err:
            await message.answer(str(err))
            return

        settings_message = await message.answer(
            _render_home(home_view),
            reply_markup=build_settings_home_keyboard(),
        )
        await _remember_settings_message(
            state,
            chat_id=settings_message.chat.id,
            message_id=settings_message.message_id,
        )

    @router.callback_query(F.data == build_settings_home_callback())
    async def handle_settings_home_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        await state.clear()
        await _show_settings_home(callback, service=service)

    @router.callback_query(F.data.startswith("sts:"))
    async def handle_settings_section_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        section = parse_settings_section_callback(cast(str, callback.data))
        if section is None:
            await callback.answer("Не получилось открыть раздел.", show_alert=True)
            return

        await state.clear()
        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        try:
            text, reply_markup = await _build_section_view(
                service,
                telegram_user_id=telegram_user_id,
                section=section,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _remember_settings_message_from_callback(state, callback)
        await _edit_callback_message(callback, text=text, reply_markup=reply_markup)

    @router.callback_query(F.data.startswith("stf:"))
    async def handle_family_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed = parse_family_callback(cast(str, callback.data))
        if parsed is None:
            await callback.answer("Не получилось открыть участника.", show_alert=True)
            return

        action, member_id = parsed
        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        if action == "add":
            await _start_prompt(
                callback=callback,
                state=state,
                prompt_state=SettingsStates.add_member_name,
                prompt_text=(
                    "Добавляем нового участника.\n\nНапиши имя участника одним сообщением."
                ),
                back_callback=build_settings_section_callback("family"),
            )
            return

        if member_id is None:
            await callback.answer("Не удалось прочитать участника.", show_alert=True)
            return

        if action == "member":
            await state.clear()
            try:
                member_view = await service.get_member_view(telegram_user_id, member_id)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_family_member_detail(member_view.member),
                reply_markup=build_family_member_keyboard(
                    member_id,
                    is_active=member_view.member.is_active,
                ),
            )
            return

        if action == "rename":
            await _start_prompt(
                callback=callback,
                state=state,
                prompt_state=SettingsStates.rename_member,
                prompt_text=(
                    "Напиши новое имя участника.\n\nИзменение сохранится сразу после ответа."
                ),
                back_callback=build_family_member_callback(member_id),
                extra_data={_MEMBER_ID_KEY: member_id.hex},
            )
            return

        if action in {"disable", "enable"}:
            await state.clear()
            try:
                family_view = await service.set_member_active(
                    telegram_user_id,
                    member_id,
                    is_active=action == "enable",
                )
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_family_view(family_view),
                reply_markup=build_settings_family_keyboard(
                    family_view.active_members,
                    family_view.inactive_members,
                ),
            )
            return

        await callback.answer("Неизвестное действие.", show_alert=True)

    @router.callback_query(F.data.startswith("stm:"))
    async def handle_member_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed = parse_member_callback(cast(str, callback.data))
        if parsed is None:
            await callback.answer("Не получилось открыть участника.", show_alert=True)
            return

        action, member_id = parsed
        if member_id is None:
            await callback.answer("Не удалось прочитать участника.", show_alert=True)
            return

        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        if action == "detail":
            await state.clear()
            try:
                member_view = await service.get_member_view(telegram_user_id, member_id)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_member_view(member_view),
                reply_markup=build_member_detail_keyboard(member_id),
            )
            return

        prompt_state: State
        prompt_text: str
        if action == "constraints":
            prompt_state = SettingsStates.edit_member_constraints
            prompt_text = (
                "Напиши новые ограничения для участника.\n\n"
                "Можно перечислить через запятую или с новой строки.\n"
                f"Чтобы очистить поле, отправь «{CLEAR_LABEL}»."
            )
        elif action == "cuisines":
            prompt_state = SettingsStates.edit_member_cuisines
            prompt_text = (
                "Напиши новый список любимых кухонь.\n\n"
                "Можно перечислить через запятую или с новой строки.\n"
                f"Чтобы очистить поле, отправь «{CLEAR_LABEL}»."
            )
        elif action == "note":
            prompt_state = SettingsStates.edit_member_note
            prompt_text = (
                "Напиши новую заметку про участника.\n\n"
                f"Чтобы очистить поле, отправь «{CLEAR_LABEL}»."
            )
        else:
            await callback.answer("Неизвестное действие.", show_alert=True)
            return

        await _start_prompt(
            callback=callback,
            state=state,
            prompt_state=prompt_state,
            prompt_text=prompt_text,
            back_callback=build_member_callback(member_id),
            extra_data={_MEMBER_ID_KEY: member_id.hex},
        )

    @router.callback_query(F.data.startswith("stp:"))
    async def handle_planning_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed = parse_planning_callback(cast(str, callback.data))
        if parsed is None:
            await callback.answer("Не получилось обновить настройку.", show_alert=True)
            return

        setting, raw_value = parsed
        await state.clear()
        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        try:
            home_view = await service.get_home(telegram_user_id)
            meal_count = home_view.household.default_meal_count_per_day
            desserts_enabled = home_view.household.desserts_enabled
            repeatability_mode = home_view.household.repeatability_mode

            if setting == "meal":
                meal_count = int(raw_value)
            elif setting == "desserts":
                desserts_enabled = raw_value == "yes"
            elif setting == "repeatability":
                repeatability_mode = RepeatabilityMode(raw_value)
            else:
                await callback.answer("Неизвестная настройка.", show_alert=True)
                return

            household = await service.update_household_planning_settings(
                telegram_user_id,
                meal_count_per_day=meal_count,
                desserts_enabled=desserts_enabled,
                repeatability_mode=repeatability_mode,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        await _remember_settings_message_from_callback(state, callback)
        await _edit_callback_message(
            callback,
            text=_render_planning_settings(household),
            reply_markup=build_settings_planning_keyboard(
                meal_count_per_day=household.default_meal_count_per_day,
                desserts_enabled=household.desserts_enabled,
                repeatability_mode=household.repeatability_mode,
            ),
        )

    @router.callback_query(F.data.startswith("str:"))
    async def handle_reminder_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed = parse_reminder_callback(cast(str, callback.data))
        if parsed is None:
            await callback.answer("Не получилось обновить напоминание.", show_alert=True)
            return

        scope, action = parsed
        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        try:
            home_view = await service.get_home(telegram_user_id)
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        if scope == "daily":
            if action == "off":
                await state.clear()
                user = await service.update_daily_feedback_reminder(telegram_user_id, None)
                await _remember_settings_message_from_callback(state, callback)
                await _edit_callback_message(
                    callback,
                    text=_render_reminders(user),
                    reply_markup=_build_reminders_keyboard(user),
                )
                return
            if action == "on":
                if home_view.user.daily_feedback_reminder_time is not None:
                    await state.clear()
                    user = await service.update_daily_feedback_reminder(
                        telegram_user_id,
                        home_view.user.daily_feedback_reminder_time,
                    )
                    await _remember_settings_message_from_callback(state, callback)
                    await _edit_callback_message(
                        callback,
                        text=_render_reminders(user),
                        reply_markup=_build_reminders_keyboard(user),
                    )
                    return
                await _start_prompt(
                    callback=callback,
                    state=state,
                    prompt_state=SettingsStates.daily_reminder_time,
                    prompt_text=(
                        "Напиши время ежедневного напоминания в формате ЧЧ:ММ.\nНапример: 20:30."
                    ),
                    back_callback=build_settings_section_callback("reminders"),
                )
                return
            if action == "time":
                await _start_prompt(
                    callback=callback,
                    state=state,
                    prompt_state=SettingsStates.daily_reminder_time,
                    prompt_text=(
                        "Напиши новое время ежедневного напоминания в формате ЧЧ:ММ.\n"
                        "Например: 20:30."
                    ),
                    back_callback=build_settings_section_callback("reminders"),
                )
                return

        if scope == "weekly":
            if action == "off":
                await state.clear()
                user = await service.update_weekly_planning_reminder(
                    telegram_user_id,
                    day_of_week=None,
                    reminder_time=None,
                )
                await _remember_settings_message_from_callback(state, callback)
                await _edit_callback_message(
                    callback,
                    text=_render_reminders(user),
                    reply_markup=_build_reminders_keyboard(user),
                )
                return
            if action == "on":
                if (
                    home_view.user.weekly_planning_reminder_day_of_week is not None
                    and home_view.user.weekly_planning_reminder_time is not None
                ):
                    await state.clear()
                    user = await service.update_weekly_planning_reminder(
                        telegram_user_id,
                        day_of_week=home_view.user.weekly_planning_reminder_day_of_week,
                        reminder_time=home_view.user.weekly_planning_reminder_time,
                    )
                    await _remember_settings_message_from_callback(state, callback)
                    await _edit_callback_message(
                        callback,
                        text=_render_reminders(user),
                        reply_markup=_build_reminders_keyboard(user),
                    )
                    return
                await _prompt_weekday_selection(
                    callback=callback,
                    state=state,
                    mode="weekly_enable",
                )
                return
            if action == "day":
                await _prompt_weekday_selection(
                    callback=callback,
                    state=state,
                    mode="weekly_day",
                )
                return
            if action == "time":
                if home_view.user.weekly_planning_reminder_day_of_week is None:
                    await _prompt_weekday_selection(
                        callback=callback,
                        state=state,
                        mode="weekly_day",
                    )
                    return
                await _start_prompt(
                    callback=callback,
                    state=state,
                    prompt_state=SettingsStates.weekly_reminder_time,
                    prompt_text=(
                        "Напиши новое время еженедельного напоминания в формате ЧЧ:ММ.\n"
                        "Например: 10:00."
                    ),
                    back_callback=build_settings_section_callback("reminders"),
                    extra_data={
                        _PENDING_WEEKLY_DAY_KEY: (
                            home_view.user.weekly_planning_reminder_day_of_week
                        ),
                    },
                )
                return

        await callback.answer("Неизвестное действие.", show_alert=True)

    @router.callback_query(F.data.startswith("stw:"))
    async def handle_weekday_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        day_of_week = parse_weekday_callback(cast(str, callback.data))
        if day_of_week is None:
            await callback.answer("Не получилось выбрать день недели.", show_alert=True)
            return

        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        state_data = await state.get_data()
        mode = cast(str | None, state_data.get(_WEEKDAY_MODE_KEY))
        if mode is None:
            await callback.answer("Выбор дня устарел. Открой настройки заново.")
            return

        try:
            home_view = await service.get_home(telegram_user_id)
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        if home_view.user.weekly_planning_reminder_time is not None and mode == "weekly_day":
            await state.clear()
            user = await service.update_weekly_planning_reminder(
                telegram_user_id,
                day_of_week=day_of_week,
                reminder_time=home_view.user.weekly_planning_reminder_time,
            )
            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_reminders(user),
                reply_markup=_build_reminders_keyboard(user),
            )
            return

        await _start_prompt(
            callback=callback,
            state=state,
            prompt_state=SettingsStates.weekly_reminder_time,
            prompt_text=(
                f"День сохранен: {_format_day_of_week(day_of_week)}.\n"
                "Теперь напиши время в формате ЧЧ:ММ."
            ),
            back_callback=build_settings_section_callback("reminders"),
            extra_data={_PENDING_WEEKLY_DAY_KEY: day_of_week},
        )

    @router.callback_query(F.data.startswith("sty:"))
    async def handle_pantry_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed = parse_pantry_callback(cast(str, callback.data))
        if parsed is None:
            await callback.answer("Не получилось открыть запасы.", show_alert=True)
            return

        action, pantry_item_id, extra, page = parsed
        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        current_page = page or 0
        if action == "page":
            await state.clear()
            try:
                pantry_view = await service.get_pantry_view(telegram_user_id)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            safe_page = _normalize_page(current_page, len(pantry_view.items))
            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_pantry_view(pantry_view, page=safe_page),
                reply_markup=build_settings_pantry_keyboard(
                    pantry_view.items,
                    page=safe_page,
                ),
            )
            return

        if action == "add":
            await _start_prompt(
                callback=callback,
                state=state,
                prompt_state=SettingsStates.pantry_add_name,
                prompt_text="Напиши название продукта, который нужно добавить в запасы.",
                back_callback=build_pantry_page_callback(current_page),
                extra_data={_PANTRY_PAGE_KEY: current_page},
            )
            return

        if action == "stock" and pantry_item_id is None:
            stock_level = _parse_stock_level(extra)
            if stock_level is None:
                await callback.answer("Не получилось прочитать статус продукта.", show_alert=True)
                return
            state_data = await state.get_data()
            pending_name = cast(str | None, state_data.get(_PENDING_PANTRY_NAME_KEY))
            if pending_name is None:
                await callback.answer("Добавление продукта устарело. Начни заново.")
                return
            await state.set_state(SettingsStates.pantry_add_hint)
            await state.update_data(
                {
                    _PENDING_PANTRY_NAME_KEY: pending_name,
                    _PENDING_PANTRY_STOCK_KEY: stock_level.value,
                },
            )
            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=(
                    f"Продукт: {pending_name}\n"
                    f"Статус: {_format_stock_level(stock_level)}\n\n"
                    "Если хочешь, напиши примерный остаток или пометку.\n"
                    f"Например: 500 г, полбанки, открыть и проверить.\n"
                    f"Или отправь «{SKIP_LABEL}»."
                ),
                reply_markup=build_prompt_back_keyboard(
                    back_callback=build_pantry_page_callback(current_page),
                ),
            )
            await callback.answer()
            return

        if pantry_item_id is None:
            await callback.answer("Не удалось прочитать продукт.", show_alert=True)
            return

        if action == "item":
            await state.clear()
            try:
                item = await service.get_pantry_item(telegram_user_id, pantry_item_id)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_pantry_item(item),
                reply_markup=build_pantry_item_keyboard(item.id, page=current_page),
            )
            return

        if action == "stock":
            stock_level = _parse_stock_level(extra)
            if stock_level is None:
                await callback.answer("Не получилось прочитать статус продукта.", show_alert=True)
                return
            await state.clear()
            try:
                item = await service.update_pantry_item_stock(
                    telegram_user_id,
                    pantry_item_id,
                    stock_level,
                )
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_pantry_item(item),
                reply_markup=build_pantry_item_keyboard(item.id, page=current_page),
            )
            return

        if action == "hint":
            await _start_prompt(
                callback=callback,
                state=state,
                prompt_state=SettingsStates.pantry_edit_hint,
                prompt_text=(
                    "Напиши новую пометку или примерный остаток.\n\n"
                    f"Чтобы очистить поле, отправь «{CLEAR_LABEL}»."
                ),
                back_callback=build_pantry_item_callback(pantry_item_id, page=current_page),
                extra_data={
                    _PANTRY_ITEM_ID_KEY: pantry_item_id.hex,
                    _PANTRY_PAGE_KEY: current_page,
                },
            )
            return

        if action == "delete":
            await state.clear()
            try:
                pantry_view = await service.delete_pantry_item(telegram_user_id, pantry_item_id)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_pantry_view(
                    pantry_view,
                    page=_normalize_page(current_page, len(pantry_view.items)),
                ),
                reply_markup=build_settings_pantry_keyboard(
                    pantry_view.items,
                    page=_normalize_page(current_page, len(pantry_view.items)),
                ),
            )
            return

        await callback.answer("Неизвестное действие.", show_alert=True)

    @router.callback_query(F.data.startswith("std:"))
    async def handle_policy_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        parsed = parse_policy_callback(cast(str, callback.data))
        if parsed is None:
            await callback.answer("Не получилось открыть правило.", show_alert=True)
            return

        action, raw_value = parsed
        telegram_user_id = _require_telegram_user_id_from_callback(callback)
        if action == "list":
            if not isinstance(raw_value, DishFeedbackVerdict):
                await callback.answer("Не получилось прочитать список.", show_alert=True)
                return
            await state.clear()
            try:
                policy_view = await service.get_dish_policy_list(telegram_user_id, raw_value)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_policy_list(policy_view.verdict, policy_view.items),
                reply_markup=build_policy_list_keyboard(policy_view.verdict, policy_view.items),
            )
            return

        if not isinstance(raw_value, UUID):
            await callback.answer("Не получилось прочитать правило.", show_alert=True)
            return

        if action == "item":
            await state.clear()
            try:
                detail_view = await service.get_dish_policy_detail(telegram_user_id, raw_value)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_policy_detail(detail_view.policy),
                reply_markup=build_policy_detail_keyboard(
                    policy_id=detail_view.policy.id,
                    verdict=detail_view.policy.verdict,
                ),
            )
            return

        if action == "remove":
            await state.clear()
            try:
                verdict = await service.remove_dish_policy(telegram_user_id, raw_value)
                updated_view = await service.get_dish_policy_list(telegram_user_id, verdict)
            except ValueError as err:
                await callback.answer(str(err), show_alert=True)
                return

            await _remember_settings_message_from_callback(state, callback)
            await _edit_callback_message(
                callback,
                text=_render_policy_list(updated_view.verdict, updated_view.items),
                reply_markup=build_policy_list_keyboard(
                    updated_view.verdict,
                    updated_view.items,
                ),
            )
            return

        await callback.answer("Неизвестное действие.", show_alert=True)

    @router.message(SettingsStates.add_member_name)
    async def handle_add_member_name(message: Message, state: FSMContext) -> None:
        try:
            display_name = _require_text(message).strip()
        except ValueError:
            await message.answer("Напиши имя участника обычным текстом.")
            return
        if not display_name:
            await message.answer("Имя не должно быть пустым.")
            return

        await state.set_state(SettingsStates.add_member_constraints)
        await state.update_data({_PENDING_MEMBER_NAME_KEY: display_name})
        await _render_prompt_after_message(
            message=message,
            state=state,
            text=(
                f"Что нельзя или нежелательно для {display_name}?\n\n"
                "Можно перечислить через запятую или с новой строки.\n"
                f"Если ничего особенного нет, отправь «{SKIP_LABEL}»."
            ),
            reply_markup=build_prompt_back_keyboard(
                back_callback=build_settings_section_callback("family"),
            ),
        )

    @router.message(SettingsStates.add_member_constraints)
    async def handle_add_member_constraints(message: Message, state: FSMContext) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши ограничения текстом или отправь Пропустить.")
            return

        constraints = [] if _is_skip(raw_text) else split_list_input(raw_text)
        state_data = await state.get_data()
        display_name = cast(str | None, state_data.get(_PENDING_MEMBER_NAME_KEY))
        if display_name is None:
            await state.clear()
            await message.answer("Не удалось продолжить добавление. Открой /settings заново.")
            return

        await state.set_state(SettingsStates.add_member_cuisines)
        await state.update_data({_PENDING_MEMBER_CONSTRAINTS_KEY: constraints})
        await _render_prompt_after_message(
            message=message,
            state=state,
            text=(
                f"Какие кухни или типы блюд любит {display_name}?\n\n"
                "Можно перечислить через запятую или с новой строки.\n"
                f"Если явных предпочтений нет, отправь «{SKIP_LABEL}»."
            ),
            reply_markup=build_prompt_back_keyboard(
                back_callback=build_settings_section_callback("family"),
            ),
        )

    @router.message(SettingsStates.add_member_cuisines)
    async def handle_add_member_cuisines(message: Message, state: FSMContext) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши кухни текстом или отправь Пропустить.")
            return

        favorite_cuisines = [] if _is_skip(raw_text) else split_list_input(raw_text)
        state_data = await state.get_data()
        display_name = cast(str | None, state_data.get(_PENDING_MEMBER_NAME_KEY))
        if display_name is None:
            await state.clear()
            await message.answer("Не удалось продолжить добавление. Открой /settings заново.")
            return

        await state.set_state(SettingsStates.add_member_note)
        await state.update_data({_PENDING_MEMBER_CUISINES_KEY: favorite_cuisines})
        await _render_prompt_after_message(
            message=message,
            state=state,
            text=(
                f"Есть ли заметка про {display_name}, которую стоит учитывать?\n\n"
                f"Если заметки нет, отправь «{SKIP_LABEL}»."
            ),
            reply_markup=build_prompt_back_keyboard(
                back_callback=build_settings_section_callback("family"),
            ),
        )

    @router.message(SettingsStates.add_member_note)
    async def handle_add_member_note(message: Message, state: FSMContext) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши заметку текстом или отправь Пропустить.")
            return

        state_data = await state.get_data()
        display_name = cast(str | None, state_data.get(_PENDING_MEMBER_NAME_KEY))
        if display_name is None:
            await state.clear()
            await message.answer("Не удалось завершить добавление. Открой /settings заново.")
            return

        telegram_user_id = _require_telegram_user_id_from_message(message)
        try:
            family_view = await service.add_member(
                telegram_user_id,
                NewSettingsMemberInput(
                    display_name=display_name,
                    constraints=cast(
                        list[str],
                        state_data.get(_PENDING_MEMBER_CONSTRAINTS_KEY, []),
                    ),
                    favorite_cuisines=cast(
                        list[str],
                        state_data.get(_PENDING_MEMBER_CUISINES_KEY, []),
                    ),
                    profile_note=None if _is_skip(raw_text) else raw_text.strip(),
                ),
            )
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.clear()
        await _edit_settings_message_from_state(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_family_view(family_view),
            reply_markup=build_settings_family_keyboard(
                family_view.active_members,
                family_view.inactive_members,
            ),
        )

    @router.message(SettingsStates.rename_member)
    async def handle_rename_member(message: Message, state: FSMContext) -> None:
        try:
            display_name = _require_text(message).strip()
        except ValueError:
            await message.answer("Напиши новое имя текстом.")
            return
        if not display_name:
            await message.answer("Имя не должно быть пустым.")
            return

        state_data = await state.get_data()
        member_id = _get_uuid_from_state(state_data, _MEMBER_ID_KEY)
        if member_id is None:
            await state.clear()
            await message.answer("Не удалось восстановить участника. Открой /settings заново.")
            return

        telegram_user_id = _require_telegram_user_id_from_message(message)
        try:
            family_view = await service.rename_member(telegram_user_id, member_id, display_name)
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.clear()
        await _edit_settings_message_from_state(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_family_view(family_view),
            reply_markup=build_settings_family_keyboard(
                family_view.active_members,
                family_view.inactive_members,
            ),
        )

    @router.message(SettingsStates.edit_member_constraints)
    async def handle_edit_member_constraints(message: Message, state: FSMContext) -> None:
        await _handle_member_text_update(
            message=message,
            state=state,
            service=service,
            field="constraints",
        )

    @router.message(SettingsStates.edit_member_cuisines)
    async def handle_edit_member_cuisines(message: Message, state: FSMContext) -> None:
        await _handle_member_text_update(
            message=message,
            state=state,
            service=service,
            field="cuisines",
        )

    @router.message(SettingsStates.edit_member_note)
    async def handle_edit_member_note(message: Message, state: FSMContext) -> None:
        await _handle_member_text_update(
            message=message,
            state=state,
            service=service,
            field="note",
        )

    @router.message(SettingsStates.daily_reminder_time)
    async def handle_daily_reminder_time(message: Message, state: FSMContext) -> None:
        try:
            reminder_time = parse_time_input(_require_text(message))
        except ValueError as err:
            await message.answer(str(err))
            return

        state_data = await state.get_data()
        try:
            user = await service.update_daily_feedback_reminder(
                _require_telegram_user_id_from_message(message),
                reminder_time,
            )
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.clear()
        await _edit_settings_message_from_state(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_reminders(user),
            reply_markup=_build_reminders_keyboard(user),
        )

    @router.message(SettingsStates.weekly_reminder_time)
    async def handle_weekly_reminder_time(message: Message, state: FSMContext) -> None:
        try:
            reminder_time = parse_time_input(_require_text(message))
        except ValueError as err:
            await message.answer(str(err))
            return

        state_data = await state.get_data()
        day_of_week = cast(int | None, state_data.get(_PENDING_WEEKLY_DAY_KEY))
        if day_of_week is None:
            await state.clear()
            await message.answer("Не удалось восстановить день недели. Открой /settings заново.")
            return

        try:
            user = await service.update_weekly_planning_reminder(
                _require_telegram_user_id_from_message(message),
                day_of_week=day_of_week,
                reminder_time=reminder_time,
            )
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.clear()
        await _edit_settings_message_from_state(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_reminders(user),
            reply_markup=_build_reminders_keyboard(user),
        )

    @router.message(SettingsStates.pantry_add_name)
    async def handle_pantry_add_name(message: Message, state: FSMContext) -> None:
        try:
            ingredient_name = _require_text(message).strip()
        except ValueError:
            await message.answer("Напиши название продукта текстом.")
            return
        if not ingredient_name:
            await message.answer("Название продукта не должно быть пустым.")
            return

        await state.update_data({_PENDING_PANTRY_NAME_KEY: ingredient_name})
        state_data = await state.get_data()
        pantry_page = cast(int, state_data.get(_PANTRY_PAGE_KEY, 0))
        await _render_prompt_after_message(
            message=message,
            state=state,
            text=(f"Продукт: {ingredient_name}\n\nВыбери текущий статус продукта."),
            reply_markup=build_pantry_stock_choice_keyboard(
                back_callback=build_pantry_page_callback(pantry_page),
            ),
        )

    @router.message(SettingsStates.pantry_add_hint)
    async def handle_pantry_add_hint(message: Message, state: FSMContext) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши пометку текстом или отправь Пропустить.")
            return

        state_data = await state.get_data()
        ingredient_name = cast(str | None, state_data.get(_PENDING_PANTRY_NAME_KEY))
        stock_value = cast(str | None, state_data.get(_PENDING_PANTRY_STOCK_KEY))
        pantry_page = cast(int, state_data.get(_PANTRY_PAGE_KEY, 0))
        if ingredient_name is None or stock_value is None:
            await state.clear()
            await message.answer("Не удалось восстановить продукт. Открой /settings заново.")
            return

        try:
            stock_level = PantryStockLevel(stock_value)
        except ValueError:
            await state.clear()
            await message.answer(
                "Не удалось восстановить статус продукта. Открой /settings заново."
            )
            return

        if _is_skip(raw_text):
            quantity_value = None
            quantity_unit = None
            note = None
        else:
            try:
                quantity_value, quantity_unit, note = parse_quantity_hint(raw_text)
            except ValueError as err:
                await message.answer(str(err))
                return

        try:
            pantry_view = await service.add_or_update_pantry_item(
                _require_telegram_user_id_from_message(message),
                PantryItemInput(
                    ingredient_name=ingredient_name,
                    normalized_name=normalize_name(ingredient_name),
                    stock_level=stock_level,
                    quantity_value=quantity_value,
                    quantity_unit=quantity_unit,
                    note=note,
                ),
            )
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.clear()
        await _edit_settings_message_from_state(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_pantry_view(
                pantry_view,
                page=_normalize_page(pantry_page, len(pantry_view.items)),
            ),
            reply_markup=build_settings_pantry_keyboard(
                pantry_view.items,
                page=_normalize_page(pantry_page, len(pantry_view.items)),
            ),
        )

    @router.message(SettingsStates.pantry_edit_hint)
    async def handle_pantry_edit_hint(message: Message, state: FSMContext) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши новую пометку или отправь Очистить.")
            return

        state_data = await state.get_data()
        pantry_item_id = _get_uuid_from_state(state_data, _PANTRY_ITEM_ID_KEY)
        pantry_page = cast(int, state_data.get(_PANTRY_PAGE_KEY, 0))
        if pantry_item_id is None:
            await state.clear()
            await message.answer("Не удалось восстановить продукт. Открой /settings заново.")
            return

        if _is_clear(raw_text):
            quantity_value = None
            quantity_unit = None
            note = None
        else:
            try:
                quantity_value, quantity_unit, note = parse_quantity_hint(raw_text)
            except ValueError as err:
                await message.answer(str(err))
                return

        try:
            item = await service.update_pantry_item_quantity(
                _require_telegram_user_id_from_message(message),
                pantry_item_id,
                quantity_value=quantity_value,
                quantity_unit=quantity_unit,
                note=note,
            )
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.clear()
        await _edit_settings_message_from_state(
            bot=_require_message_bot(message),
            state_data=state_data,
            text=_render_pantry_item(item),
            reply_markup=build_pantry_item_keyboard(item.id, page=pantry_page),
        )

    return router


async def _build_section_view(
    service: SettingsService,
    *,
    telegram_user_id: int,
    section: str,
) -> tuple[str, InlineKeyboardMarkup]:
    if section == "family":
        family_view = await service.get_family_view(telegram_user_id)
        return (
            _render_family_view(family_view),
            build_settings_family_keyboard(
                family_view.active_members,
                family_view.inactive_members,
            ),
        )
    if section == "members":
        members = await service.list_member_profiles(telegram_user_id)
        return (
            _render_members_view(members),
            build_settings_members_keyboard(members),
        )
    if section == "planning":
        home_view = await service.get_home(telegram_user_id)
        return (
            _render_planning_settings(home_view.household),
            build_settings_planning_keyboard(
                meal_count_per_day=home_view.household.default_meal_count_per_day,
                desserts_enabled=home_view.household.desserts_enabled,
                repeatability_mode=home_view.household.repeatability_mode,
            ),
        )
    if section == "reminders":
        home_view = await service.get_home(telegram_user_id)
        return (
            _render_reminders(home_view.user),
            _build_reminders_keyboard(home_view.user),
        )
    if section == "pantry":
        pantry_view = await service.get_pantry_view(telegram_user_id)
        return (
            _render_pantry_view(pantry_view, page=0),
            build_settings_pantry_keyboard(pantry_view.items, page=0),
        )
    if section == "policies":
        home_view = await service.get_home(telegram_user_id)
        return (
            _render_policy_home(home_view),
            build_settings_policy_home_keyboard(
                favorite_count=home_view.favorite_policies_count,
                blocked_count=home_view.blocked_policies_count,
            ),
        )
    raise ValueError("Неизвестный раздел настроек.")


async def _show_settings_home(
    callback: CallbackQuery,
    *,
    service: SettingsService,
) -> None:
    try:
        home_view = await service.get_home(_require_telegram_user_id_from_callback(callback))
    except ValueError as err:
        await callback.answer(str(err), show_alert=True)
        return

    await _edit_callback_message(
        callback,
        text=_render_home(home_view),
        reply_markup=build_settings_home_keyboard(),
    )


async def _prompt_weekday_selection(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    mode: str,
) -> None:
    await state.clear()
    await _remember_settings_message_from_callback(state, callback)
    await state.update_data({_WEEKDAY_MODE_KEY: mode})
    await _edit_callback_message(
        callback,
        text="Выбери день недели для еженедельного напоминания.",
        reply_markup=build_weekday_keyboard(
            back_callback=build_settings_section_callback("reminders"),
        ),
    )


async def _start_prompt(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    prompt_state: State,
    prompt_text: str,
    back_callback: str,
    extra_data: dict[str, Any] | None = None,
) -> None:
    await state.clear()
    await _remember_settings_message_from_callback(state, callback)
    if extra_data:
        await state.update_data(extra_data)
    await state.set_state(prompt_state)
    await _edit_callback_message(
        callback,
        text=prompt_text,
        reply_markup=build_prompt_back_keyboard(back_callback=back_callback),
    )


async def _render_prompt_after_message(
    *,
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    state_data = await state.get_data()
    await _edit_settings_message_from_state(
        bot=_require_message_bot(message),
        state_data=state_data,
        text=text,
        reply_markup=reply_markup,
    )


async def _handle_member_text_update(
    *,
    message: Message,
    state: FSMContext,
    service: SettingsService,
    field: str,
) -> None:
    try:
        raw_text = _require_text(message)
    except ValueError:
        await message.answer("Напиши значение текстом.")
        return

    state_data = await state.get_data()
    member_id = _get_uuid_from_state(state_data, _MEMBER_ID_KEY)
    if member_id is None:
        await state.clear()
        await message.answer("Не удалось восстановить участника. Открой /settings заново.")
        return

    telegram_user_id = _require_telegram_user_id_from_message(message)
    try:
        if field == "constraints":
            constraints = [] if _is_clear_or_skip(raw_text) else split_list_input(raw_text)
            member_view = await service.update_member_constraints(
                telegram_user_id,
                member_id,
                constraints,
            )
        elif field == "cuisines":
            favorite_cuisines = [] if _is_clear_or_skip(raw_text) else split_list_input(raw_text)
            member_view = await service.update_member_cuisines(
                telegram_user_id,
                member_id,
                favorite_cuisines,
            )
        elif field == "note":
            member_view = await service.update_member_note(
                telegram_user_id,
                member_id,
                None if _is_clear_or_skip(raw_text) else raw_text.strip(),
            )
        else:
            raise ValueError("Неизвестное поле участника.")
    except ValueError as err:
        await message.answer(str(err))
        return

    await state.clear()
    await _edit_settings_message_from_state(
        bot=_require_message_bot(message),
        state_data=state_data,
        text=_render_member_view(member_view),
        reply_markup=build_member_detail_keyboard(member_view.member.id),
    )


def _render_home(view: SettingsHomeView) -> str:
    return "\n".join(
        [
            "Настройки",
            "",
            f"Семья: {view.active_members_count} активн., {view.inactive_members_count} отключ.",
            f"Запасы: {view.pantry_items_count} продуктов.",
            f"Любимые блюда: {view.favorite_policies_count}.",
            f"Не предлагать: {view.blocked_policies_count}.",
            "",
            "Выбери раздел ниже.",
        ],
    )


def _render_family_view(view: FamilySettingsView) -> str:
    lines = ["Состав семьи", ""]
    if view.active_members:
        lines.append("Активные:")
        lines.extend([f"• {member.display_name}" for member in view.active_members])
    else:
        lines.append("Активных участников пока нет.")
    if view.inactive_members:
        lines.extend(["", "Отключенные:"])
        lines.extend([f"• {member.display_name}" for member in view.inactive_members])
    lines.extend(["", "Выбери участника, чтобы переименовать или включить/отключить."])
    return "\n".join(lines)


def _render_family_member_detail(member: StoredSettingsMember) -> str:
    status_text = "активен" if member.is_active else "отключен"
    return "\n".join(
        [
            f"Участник: {member.display_name}",
            f"Статус: {status_text}",
            "",
            "Здесь можно переименовать участника или изменить его статус.",
        ],
    )


def _render_members_view(members: list[StoredSettingsMember]) -> str:
    lines = ["Участники", ""]
    if not members:
        lines.extend(
            [
                "Активных участников пока нет.",
                "",
                "Сначала добавь участника в разделе «Семья».",
            ],
        )
        return "\n".join(lines)
    lines.extend([f"• {member.display_name}" for member in members])
    lines.extend(["", "Выбери участника, чтобы изменить ограничения, кухни или заметку."])
    return "\n".join(lines)


def _render_member_view(view: MemberSettingsView) -> str:
    member = view.member
    constraints = ", ".join(member.constraints) if member.constraints else "нет"
    cuisines = ", ".join(member.favorite_cuisines) if member.favorite_cuisines else "нет"
    note = member.profile_note or "нет"
    return "\n".join(
        [
            f"Участник: {member.display_name}",
            "",
            f"Ограничения: {constraints}",
            f"Любимые кухни: {cuisines}",
            f"Заметка: {note}",
            "",
            "Выбери, что изменить.",
        ],
    )


def _render_planning_settings(household) -> str:
    return "\n".join(
        [
            "Планирование по умолчанию",
            "",
            f"Приемов пищи в день: {household.default_meal_count_per_day}",
            f"Десерты: {'Да' if household.desserts_enabled else 'Нет'}",
            f"Режим повторяемости: {_format_repeatability(household.repeatability_mode)}",
            "",
            "Кнопки ниже сохраняют настройку сразу.",
        ],
    )


def _render_reminders(user: StoredSettingsUser) -> str:
    daily_text = _format_time_or_disabled(
        enabled=user.daily_feedback_reminder_enabled,
        value=user.daily_feedback_reminder_time,
    )
    weekly_text = (
        f"{_format_day_of_week(user.weekly_planning_reminder_day_of_week)}"
        f" · {_format_time(user.weekly_planning_reminder_time)}"
        if (
            user.weekly_planning_reminder_enabled
            and user.weekly_planning_reminder_day_of_week is not None
            and user.weekly_planning_reminder_time is not None
        )
        else "выкл"
    )
    return "\n".join(
        [
            "Напоминания",
            "",
            f"Ежедневное напоминание на оценку блюд: {daily_text}",
            f"Еженедельное напоминание на план: {weekly_text}",
            "",
            "Выбери, что изменить.",
        ],
    )


def _render_pantry_view(view: PantrySettingsView, *, page: int = 0) -> str:
    lines = ["Запасы", ""]
    if not view.items:
        lines.extend(["Пока ничего не добавлено.", "", "Можно начать с кнопки «Добавить продукт»."])
        return "\n".join(lines)
    visible_items, page_number, total_pages = _slice_pantry_page(view.items, page=page)
    lines.append(f"Страница {page_number + 1} из {total_pages}")
    lines.append("")
    for item in visible_items:
        lines.append(
            f"• {item.ingredient_name} — "
            f"{_format_stock_level(item.stock_level)}{_render_hint_suffix(item)}",
        )
    lines.extend(["", "Выбери продукт, чтобы обновить статус или пометку."])
    return "\n".join(lines)


def _render_pantry_item(item: StoredSettingsPantryItem) -> str:
    return "\n".join(
        [
            f"Продукт: {item.ingredient_name}",
            f"Статус: {_format_stock_level(item.stock_level)}",
            f"Пометка: {_format_pantry_hint(item)}",
            "",
            "Здесь можно обновить статус, изменить пометку или удалить продукт из запасов.",
        ],
    )


def _render_policy_home(view: SettingsHomeView) -> str:
    return "\n".join(
        [
            "Блюда",
            "",
            f"Любимые: {view.favorite_policies_count}",
            f"Не предлагать: {view.blocked_policies_count}",
            "",
            "Выбери список, чтобы открыть блюда и снять правило при необходимости.",
        ],
    )


def _render_policy_list(
    verdict: DishFeedbackVerdict,
    items: list[StoredSettingsDishPolicy],
) -> str:
    title = "Любимые блюда" if verdict is DishFeedbackVerdict.FAVORITE else "Не предлагать"
    lines = [title, ""]
    if not items:
        lines.extend(
            ["Список пока пуст.", "", "Здесь появятся блюда после оценок и ручных правил."]
        )
        return "\n".join(lines)
    lines.extend([f"• {item.dish_name}" for item in items])
    lines.extend(["", "Выбери блюдо, чтобы убрать правило."])
    return "\n".join(lines)


def _render_policy_detail(policy: StoredSettingsDishPolicy) -> str:
    title = "Любимое блюдо" if policy.verdict is DishFeedbackVerdict.FAVORITE else "Не предлагать"
    note = policy.note or "нет"
    return "\n".join(
        [
            title,
            "",
            f"Блюдо: {policy.dish_name}",
            f"Заметка: {note}",
            "",
            "Если убрать правило, блюдо снова вернется в обычный пул рекомендаций.",
        ],
    )


def _build_reminders_keyboard(user: StoredSettingsUser) -> InlineKeyboardMarkup:
    return build_settings_reminders_keyboard(
        daily_enabled=user.daily_feedback_reminder_enabled,
        daily_time_text=_format_time(user.daily_feedback_reminder_time),
        weekly_enabled=user.weekly_planning_reminder_enabled,
        weekly_day_text=_format_day_of_week(user.weekly_planning_reminder_day_of_week),
        weekly_time_text=_format_time(user.weekly_planning_reminder_time),
    )


def _format_repeatability(mode: RepeatabilityMode) -> str:
    mapping = {
        RepeatabilityMode.BALANCED: "сбалансировано",
        RepeatabilityMode.MORE_VARIETY: "больше нового",
        RepeatabilityMode.MORE_REPEATABILITY: "больше повторов",
    }
    return mapping[mode]


def _format_stock_level(stock_level: PantryStockLevel) -> str:
    mapping = {
        PantryStockLevel.HAS: "есть",
        PantryStockLevel.LOW: "мало",
        PantryStockLevel.NONE: "нет",
    }
    return mapping[stock_level]


def _format_time_or_disabled(*, enabled: bool, value: time | None) -> str:
    if not enabled or value is None:
        return "выкл"
    return _format_time(value)


def _format_time(value: time | None) -> str:
    if value is None:
        return "не задано"
    return value.strftime("%H:%M")


def _format_day_of_week(day_of_week: int | None) -> str:
    labels = {
        0: "понедельник",
        1: "вторник",
        2: "среда",
        3: "четверг",
        4: "пятница",
        5: "суббота",
        6: "воскресенье",
    }
    if day_of_week is None:
        return "не задан"
    return labels.get(day_of_week, "неизвестный день")


def _render_hint_suffix(item: StoredSettingsPantryItem) -> str:
    hint = _format_pantry_hint(item)
    return "" if hint == "нет" else f" · {hint}"


def _slice_pantry_page(
    items: list[StoredSettingsPantryItem],
    *,
    page: int,
) -> tuple[list[StoredSettingsPantryItem], int, int]:
    total_pages = max(1, (len(items) + _PANTRY_PAGE_SIZE - 1) // _PANTRY_PAGE_SIZE)
    safe_page = _normalize_page(page, len(items))
    start_index = safe_page * _PANTRY_PAGE_SIZE
    end_index = start_index + _PANTRY_PAGE_SIZE
    return items[start_index:end_index], safe_page, total_pages


def _normalize_page(page: int, total_items: int) -> int:
    total_pages = max(1, (total_items + _PANTRY_PAGE_SIZE - 1) // _PANTRY_PAGE_SIZE)
    return max(0, min(page, total_pages - 1))


def _format_pantry_hint(item: StoredSettingsPantryItem) -> str:
    quantity_text = None
    if item.quantity_value is not None and item.quantity_unit:
        quantity_text = f"{item.quantity_value.normalize()} {item.quantity_unit}"
    if quantity_text and item.note:
        return f"{quantity_text}, {item.note}"
    if quantity_text:
        return quantity_text
    if item.note:
        return item.note
    return "нет"


def _parse_stock_level(value: str | None) -> PantryStockLevel | None:
    if value == "has":
        return PantryStockLevel.HAS
    if value == "low":
        return PantryStockLevel.LOW
    return None


def _is_skip(value: str) -> bool:
    return normalize_name(value) == normalize_name(SKIP_LABEL)


def _is_clear(value: str) -> bool:
    return normalize_name(value) == normalize_name(CLEAR_LABEL)


def _is_clear_or_skip(value: str) -> bool:
    return _is_clear(value) or _is_skip(value)


def _get_uuid_from_state(state_data: dict[str, Any], key: str) -> UUID | None:
    raw_value = cast(str | None, state_data.get(key))
    if raw_value is None:
        return None
    try:
        return UUID(hex=raw_value)
    except ValueError:
        return None


async def _remember_settings_message(
    state: FSMContext,
    *,
    chat_id: int,
    message_id: int,
) -> None:
    await state.update_data({_CHAT_ID_KEY: chat_id, _MESSAGE_ID_KEY: message_id})


async def _remember_settings_message_from_callback(
    state: FSMContext,
    callback: CallbackQuery,
) -> None:
    message = _require_callback_message(callback)
    await _remember_settings_message(
        state,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )


async def _edit_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    message = _require_callback_message(callback)
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as err:
        if "message is not modified" not in str(err).lower():
            raise
    await callback.answer()


async def _edit_settings_message_from_state(
    *,
    bot: Bot,
    state_data: dict[str, Any],
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    message_id = cast(int | None, state_data.get(_MESSAGE_ID_KEY))
    chat_id = cast(int | None, state_data.get(_CHAT_ID_KEY))
    if message_id is None or chat_id is None:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as err:
        if "message is not modified" not in str(err).lower():
            raise


def _require_text(message: Message) -> str:
    if message.text is None:
        raise ValueError("Текст сообщения не найден.")
    return message.text.strip()


def _require_telegram_user_id_from_message(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Не удалось определить пользователя Telegram.")
    return message.from_user.id


def _require_telegram_user_id_from_callback(callback: CallbackQuery) -> int:
    if callback.from_user is None:
        raise ValueError("Не удалось определить пользователя Telegram.")
    return callback.from_user.id


def _require_callback_message(callback: CallbackQuery) -> Message:
    if callback.message is None or not isinstance(callback.message, Message):
        raise ValueError("Сообщение для обновления не найдено.")
    return callback.message


def _require_message_bot(message: Message) -> Bot:
    bot = message.bot
    if bot is None:
        raise ValueError("Bot instance is not available.")
    return bot
