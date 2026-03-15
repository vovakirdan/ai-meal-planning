from __future__ import annotations

from decimal import Decimal
from typing import cast

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.onboarding import (
    DailyReminderInput,
    HouseholdMemberInput,
    HouseholdSettingsInput,
    OnboardingService,
    PantryItemInput,
    WeeklyReminderInput,
)
from aimealplanner.infrastructure.db.enums import PantryStockLevel, RepeatabilityMode
from aimealplanner.infrastructure.db.repositories import build_onboarding_repositories
from aimealplanner.presentation.telegram.keyboards.onboarding import (
    CANCEL_LABEL,
    NO_LABEL,
    PANTRY_STOCK_LABELS,
    REPEATABILITY_LABELS,
    SKIP_LABEL,
    YES_LABEL,
    build_day_of_week_keyboard,
    build_household_size_keyboard,
    build_meal_count_keyboard,
    build_pantry_continue_keyboard,
    build_pantry_stock_keyboard,
    build_repeatability_keyboard,
    build_skip_keyboard,
    build_yes_no_keyboard,
    remove_keyboard,
)
from aimealplanner.presentation.telegram.onboarding_parsing import (
    normalize_name,
    parse_day_of_week,
    parse_quantity_hint,
    parse_time_input,
    split_list_input,
)
from aimealplanner.presentation.telegram.states.onboarding import OnboardingStates


def build_onboarding_router(
    session_factory: async_sessionmaker[AsyncSession],
) -> Router:
    router = Router(name="onboarding")
    service = OnboardingService(session_factory, build_onboarding_repositories)

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext) -> None:
        telegram_user_id = _require_telegram_user_id(message)
        await state.clear()
        result = await service.start_onboarding(telegram_user_id)
        if result.already_completed:
            await message.answer(
                ("Профиль уже настроен.\nПозже здесь появятся план недели и настройки."),
                reply_markup=remove_keyboard(),
            )
            return

        await state.set_state(OnboardingStates.household_size)
        await message.answer(
            (
                "Привет! Начнем онбординг.\n"
                "Я задам несколько коротких вопросов про состав семьи, "
                "предпочтения, напоминания и запасы."
            ),
            reply_markup=build_household_size_keyboard(),
        )
        await message.answer(
            "Сколько человек нужно учитывать в меню? "
            "Выбери число кнопкой или напиши его сообщением.",
        )

    @router.message(Command("cancel"))
    async def handle_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Ок, текущий онбординг остановлен. Чтобы начать заново, отправь /start.",
            reply_markup=remove_keyboard(),
        )

    @router.message(OnboardingStates.household_size)
    async def handle_household_size(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        try:
            household_size = int(text)
        except ValueError:
            await message.answer("Нужно указать количество человек цифрой, например 2.")
            return

        if household_size not in range(1, 11):
            await message.answer("Для MVP давай ограничимся составом от 1 до 10 человек.")
            return

        await state.update_data(household_size=household_size, member_index=0, member_names=[])
        await state.set_state(OnboardingStates.meal_count)
        await message.answer(
            "Сколько приемов пищи в день обычно планировать? Выбери число от 2 до 5.",
            reply_markup=build_meal_count_keyboard(),
        )

    @router.message(OnboardingStates.meal_count)
    async def handle_meal_count(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        try:
            meal_count = int(text)
        except ValueError:
            await message.answer("Нужно выбрать количество приемов пищи от 2 до 5.")
            return

        if meal_count not in range(2, 6):
            await message.answer("Количество приемов пищи должно быть в диапазоне от 2 до 5.")
            return

        await state.update_data(meal_count=meal_count)
        await state.set_state(OnboardingStates.desserts_enabled)
        await message.answer(
            "Включать десерты в план по умолчанию?",
            reply_markup=build_yes_no_keyboard(),
        )

    @router.message(OnboardingStates.desserts_enabled)
    async def handle_desserts_enabled(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        desserts_enabled = _parse_yes_no(text)
        if desserts_enabled is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        await state.update_data(desserts_enabled=desserts_enabled)
        await state.set_state(OnboardingStates.repeatability_mode)
        await message.answer(
            "Какой режим повторяемости нужен? Можно пропустить, тогда будет сбалансированно.",
            reply_markup=build_repeatability_keyboard(),
        )

    @router.message(OnboardingStates.repeatability_mode)
    async def handle_repeatability_mode(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        if _is_skip(text):
            repeatability_mode = RepeatabilityMode.BALANCED
        elif text in REPEATABILITY_LABELS:
            repeatability_mode = RepeatabilityMode(REPEATABILITY_LABELS[text])
        else:
            await message.answer(
                "Выбери один из режимов кнопкой или нажми Пропустить.",
            )
            return

        state_data = await state.get_data()
        await service.save_household_settings(
            _require_telegram_user_id(message),
            HouseholdSettingsInput(
                meal_count_per_day=cast(int, state_data["meal_count"]),
                desserts_enabled=cast(bool, state_data["desserts_enabled"]),
                repeatability_mode=repeatability_mode,
            ),
        )
        await state.set_state(OnboardingStates.member_name)
        household_size = cast(int, state_data["household_size"])
        member_intro = (
            "Теперь немного о тебе.\nКак тебя зовут?"
            if household_size == 1
            else "Теперь коротко про каждого участника.\nКак зовут первого участника?"
        )
        await message.answer(member_intro, reply_markup=remove_keyboard())

    @router.message(OnboardingStates.member_name)
    async def handle_member_name(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        display_name = text.strip()
        if not display_name:
            await message.answer("Имя участника не должно быть пустым.")
            return

        state_data = await state.get_data()
        member_index = cast(int, state_data["member_index"])
        await state.update_data(current_member_name=display_name)
        await state.set_state(OnboardingStates.member_constraints)
        await message.answer(
            (
                f"Что точно нельзя или нежелательно для участника {display_name}?\n"
                "Можно перечислить через запятую или с новой строки. "
                "Если ничего особенного нет, нажми Пропустить."
            ),
            reply_markup=build_skip_keyboard(),
        )
        if member_index == 0:
            await message.answer("Пример: оливки, печень, моллюски.")

    @router.message(OnboardingStates.member_constraints)
    async def handle_member_constraints(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        constraints = [] if _is_skip(text) else split_list_input(text)
        await state.update_data(current_member_constraints=constraints)
        await state.set_state(OnboardingStates.member_cuisines)
        member_name = cast(str, (await state.get_data())["current_member_name"])
        await message.answer(
            (
                f"Какие кухни или типы блюд любит {member_name}?\n"
                "Можно перечислить списком. Если явных предпочтений нет, нажми Пропустить."
            ),
            reply_markup=build_skip_keyboard(),
        )

    @router.message(OnboardingStates.member_cuisines)
    async def handle_member_cuisines(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        favorite_cuisines = [] if _is_skip(text) else split_list_input(text)
        await state.update_data(current_member_cuisines=favorite_cuisines)
        await state.set_state(OnboardingStates.member_note)
        member_name = cast(str, (await state.get_data())["current_member_name"])
        await message.answer(
            (
                f"Есть ли свободная заметка про {member_name}, которую стоит учитывать?\n"
                "Например: любит посытнее, не любит слишком острое. Можно пропустить."
            ),
            reply_markup=build_skip_keyboard(),
        )

    @router.message(OnboardingStates.member_note)
    async def handle_member_note(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        state_data = await state.get_data()
        member_index = cast(int, state_data["member_index"])
        household_size = cast(int, state_data["household_size"])
        member_names = list(cast(list[str], state_data["member_names"]))
        display_name = cast(str, state_data["current_member_name"])

        await service.save_member_profile(
            _require_telegram_user_id(message),
            HouseholdMemberInput(
                sort_order=member_index,
                display_name=display_name,
                constraints=cast(list[str], state_data["current_member_constraints"]),
                favorite_cuisines=cast(list[str], state_data["current_member_cuisines"]),
                profile_note=None if _is_skip(text) else text.strip(),
            ),
        )

        member_names.append(display_name)
        next_member_index = member_index + 1
        await state.update_data(member_index=next_member_index, member_names=member_names)

        if next_member_index < household_size:
            await state.set_state(OnboardingStates.member_name)
            await message.answer(
                f"Переходим к следующему участнику. Как зовут участника #{next_member_index + 1}?",
                reply_markup=remove_keyboard(),
            )
            return

        await state.set_state(OnboardingStates.daily_reminder_enabled)
        await message.answer(
            "Нужно ли присылать ежедневное напоминание оценить блюда?",
            reply_markup=build_yes_no_keyboard(),
        )
        await message.answer("Если ежедневное напоминание не нужно, выбери Нет.")

    @router.message(OnboardingStates.daily_reminder_enabled)
    async def handle_daily_reminder_enabled(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        is_enabled = _parse_yes_no(text)
        if is_enabled is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        if not is_enabled:
            await service.save_daily_feedback_reminder(
                _require_telegram_user_id(message),
                DailyReminderInput(reminder_time=None),
            )
            await state.set_state(OnboardingStates.weekly_reminder_enabled)
            await message.answer(
                "Нужно ли напоминать составить план на следующую неделю?",
                reply_markup=build_yes_no_keyboard(),
            )
            return

        await state.set_state(OnboardingStates.daily_reminder_time)
        await message.answer(
            "Напиши время ежедневного напоминания в формате ЧЧ:ММ, например 20:30.",
            reply_markup=remove_keyboard(),
        )

    @router.message(OnboardingStates.daily_reminder_time)
    async def handle_daily_reminder_time(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        try:
            reminder_time = parse_time_input(text)
        except ValueError as err:
            await message.answer(str(err))
            return

        await service.save_daily_feedback_reminder(
            _require_telegram_user_id(message),
            DailyReminderInput(reminder_time=reminder_time),
        )
        await state.set_state(OnboardingStates.weekly_reminder_enabled)
        await message.answer(
            "Нужно ли напоминать составить план на следующую неделю?",
            reply_markup=build_yes_no_keyboard(),
        )

    @router.message(OnboardingStates.weekly_reminder_enabled)
    async def handle_weekly_reminder_enabled(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        is_enabled = _parse_yes_no(text)
        if is_enabled is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        if not is_enabled:
            await service.save_weekly_planning_reminder(
                _require_telegram_user_id(message),
                WeeklyReminderInput(day_of_week=None, reminder_time=None),
            )
            await state.set_state(OnboardingStates.pantry_choice)
            await message.answer(
                "Хочешь сразу отметить, что уже есть дома?",
                reply_markup=build_yes_no_keyboard(),
            )
            return

        await state.set_state(OnboardingStates.weekly_reminder_day)
        await message.answer(
            "В какой день недели напоминать про план?",
            reply_markup=build_day_of_week_keyboard(),
        )

    @router.message(OnboardingStates.weekly_reminder_day)
    async def handle_weekly_reminder_day(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        try:
            day_of_week = parse_day_of_week(text)
        except ValueError as err:
            await message.answer(str(err))
            return

        await state.update_data(weekly_reminder_day_of_week=day_of_week)
        await state.set_state(OnboardingStates.weekly_reminder_time)
        await message.answer(
            "Во сколько присылать weekly reminder? Формат ЧЧ:ММ.",
            reply_markup=remove_keyboard(),
        )

    @router.message(OnboardingStates.weekly_reminder_time)
    async def handle_weekly_reminder_time(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        try:
            reminder_time = parse_time_input(text)
        except ValueError as err:
            await message.answer(str(err))
            return

        state_data = await state.get_data()
        await service.save_weekly_planning_reminder(
            _require_telegram_user_id(message),
            WeeklyReminderInput(
                day_of_week=cast(int, state_data["weekly_reminder_day_of_week"]),
                reminder_time=reminder_time,
            ),
        )
        await state.set_state(OnboardingStates.pantry_choice)
        await message.answer(
            "Хочешь сразу отметить, что уже есть дома?",
            reply_markup=build_yes_no_keyboard(),
        )

    @router.message(OnboardingStates.pantry_choice)
    async def handle_pantry_choice(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        wants_pantry = _parse_yes_no(text)
        if wants_pantry is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        if not wants_pantry:
            await _finish_onboarding(message, state, service)
            return

        await state.set_state(OnboardingStates.pantry_item_name)
        await message.answer(
            (
                "Напиши первый продукт, который уже есть дома.\n"
                "Например: томаты в собственном соку, рис, пармезан."
            ),
            reply_markup=remove_keyboard(),
        )

    @router.message(OnboardingStates.pantry_item_name)
    async def handle_pantry_item_name(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        ingredient_name = text.strip()
        if not ingredient_name:
            await message.answer("Название продукта не должно быть пустым.")
            return

        await state.update_data(
            pantry_item_name=ingredient_name,
            pantry_item_normalized_name=normalize_name(ingredient_name),
        )
        await state.set_state(OnboardingStates.pantry_stock_level)
        await message.answer(
            "Сколько этого продукта сейчас есть дома?",
            reply_markup=build_pantry_stock_keyboard(),
        )

    @router.message(OnboardingStates.pantry_stock_level)
    async def handle_pantry_stock_level(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        if text == CANCEL_LABEL:
            await state.set_state(OnboardingStates.pantry_item_name)
            await message.answer(
                "Хорошо, не добавляю этот продукт. Пришли следующий продукт.",
                reply_markup=remove_keyboard(),
            )
            return

        if text not in PANTRY_STOCK_LABELS:
            await message.answer("Выбери один из вариантов: Есть, Мало, Отмена.")
            return

        await state.update_data(pantry_stock_level=PANTRY_STOCK_LABELS[text])
        await state.set_state(OnboardingStates.pantry_quantity_hint)
        await message.answer(
            (
                "Если хочешь, уточни остаток, например `500 г` или `2 банки`.\n"
                "Если не хочешь уточнять, нажми Пропустить."
            ),
            reply_markup=build_skip_keyboard(),
        )

    @router.message(OnboardingStates.pantry_quantity_hint)
    async def handle_pantry_quantity_hint(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        quantity_value: Decimal | None
        quantity_unit: str | None
        note: str | None
        if _is_skip(text):
            quantity_value, quantity_unit, note = None, None, None
        else:
            try:
                quantity_value, quantity_unit, note = parse_quantity_hint(text)
            except ValueError as err:
                await message.answer(str(err))
                return

        state_data = await state.get_data()
        await service.add_pantry_item(
            _require_telegram_user_id(message),
            PantryItemInput(
                ingredient_name=cast(str, state_data["pantry_item_name"]),
                normalized_name=cast(str, state_data["pantry_item_normalized_name"]),
                stock_level=PantryStockLevel(cast(str, state_data["pantry_stock_level"])),
                quantity_value=quantity_value,
                quantity_unit=quantity_unit,
                note=note,
            ),
        )
        await state.set_state(OnboardingStates.pantry_continue)
        await message.answer(
            "Добавить еще один продукт в запасы?",
            reply_markup=build_pantry_continue_keyboard(),
        )

    @router.message(OnboardingStates.pantry_continue)
    async def handle_pantry_continue(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        wants_more = _parse_yes_no(text)
        if wants_more is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        if wants_more:
            await state.set_state(OnboardingStates.pantry_item_name)
            await message.answer(
                "Хорошо, пришли следующий продукт.",
                reply_markup=remove_keyboard(),
            )
            return

        await _finish_onboarding(message, state, service)

    return router


async def _finish_onboarding(
    message: Message,
    state: FSMContext,
    service: OnboardingService,
) -> None:
    state_data = await state.get_data()
    await service.complete_onboarding(_require_telegram_user_id(message))
    member_names = cast(list[str], state_data.get("member_names", []))
    await state.clear()
    await message.answer(
        (
            "Онбординг завершен.\n"
            "Сохранил состав семьи: "
            f"{', '.join(member_names) if member_names else 'без участников'}.\n"
            "Дальше здесь появится составление плана на неделю."
        ),
        reply_markup=remove_keyboard(),
    )


def _require_telegram_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram user context is required")
    return message.from_user.id


def _require_text(message: Message) -> str:
    if message.text is None:
        raise ValueError("Text message is required")
    return message.text.strip()


def _parse_yes_no(value: str) -> bool | None:
    normalized = value.strip()
    if normalized == YES_LABEL:
        return True
    if normalized == NO_LABEL:
        return False
    return None


def _is_skip(value: str) -> bool:
    return value.strip() == SKIP_LABEL
