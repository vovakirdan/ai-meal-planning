from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import cast
from uuid import UUID

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning import (
    PlanDraftInput,
    PlanningService,
    PlanningStartContext,
    WeeklyPlanGenerationService,
)
from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.db.repositories import build_planning_repositories
from aimealplanner.infrastructure.recipes import SpoonacularRecipeHintProvider
from aimealplanner.presentation.telegram.keyboards.onboarding import (
    NO_LABEL,
    SKIP_LABEL,
    YES_LABEL,
    build_meal_count_keyboard,
    build_skip_keyboard,
    build_yes_no_keyboard,
    remove_keyboard,
)
from aimealplanner.presentation.telegram.keyboards.planning import (
    CUSTOM_DATES_LABEL,
    NEXT_WEEK_LABEL,
    TODAY_LABEL,
    TOMORROW_LABEL,
    WEEK_MOOD_LABELS,
    build_plan_days_keyboard,
    build_range_choice_keyboard,
    build_week_mood_keyboard,
)
from aimealplanner.presentation.telegram.planning_parsing import parse_date_input
from aimealplanner.presentation.telegram.states.planning import PlanningStates

logger = logging.getLogger(__name__)


def build_planning_router(
    session_factory: async_sessionmaker[AsyncSession],
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
    *,
    recipe_hint_provider: SpoonacularRecipeHintProvider | None,
) -> Router:
    router = Router(name="planning")
    service = PlanningService(session_factory, build_planning_repositories)
    generation_service = WeeklyPlanGenerationService(
        session_factory,
        build_planning_repositories,
        weekly_plan_generator,
        recipe_hint_provider=recipe_hint_provider,
    )

    @router.message(Command("plan"))
    async def handle_plan_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            context = await service.start_planning(_require_telegram_user_id(message))
        except ValueError as err:
            await message.answer(str(err), reply_markup=remove_keyboard())
            return

        await _store_start_context(state, context)
        if context.existing_draft is not None:
            await state.set_state(PlanningStates.replace_existing_draft)
            await message.answer(
                (
                    "У тебя уже есть черновик плана на период "
                    f"{format_date(context.existing_draft.start_date)} - "
                    f"{format_date(context.existing_draft.end_date)}.\n"
                    "Удалить его и настроить новый?"
                ),
                reply_markup=build_yes_no_keyboard(),
            )
            return

        await _start_range_selection(
            message,
            state,
            default_start_date=context.default_start_date,
            default_end_date=context.default_end_date,
        )

    @router.message(PlanningStates.replace_existing_draft)
    async def handle_replace_existing_draft(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        should_replace = _parse_yes_no(text)
        if should_replace is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        if not should_replace:
            await state.clear()
            await message.answer(
                "Ок, оставляю текущий черновик без изменений. Открыть его можно командой /week.",
                reply_markup=remove_keyboard(),
            )
            return

        try:
            await service.discard_existing_drafts(_require_telegram_user_id(message))
        except ValueError as err:
            await state.clear()
            await message.answer(str(err), reply_markup=remove_keyboard())
            return

        state_data = await state.get_data()
        await _start_range_selection(
            message,
            state,
            default_start_date=date.fromisoformat(cast(str, state_data["default_start_date"])),
            default_end_date=date.fromisoformat(cast(str, state_data["default_end_date"])),
        )

    @router.message(PlanningStates.range_choice)
    async def handle_range_choice(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        state_data = await state.get_data()
        today_local_date = date.fromisoformat(cast(str, state_data["today_local_date"]))

        if text == NEXT_WEEK_LABEL:
            start_date = date.fromisoformat(cast(str, state_data["default_start_date"]))
            end_date = date.fromisoformat(cast(str, state_data["default_end_date"]))
            await state.update_data(
                selected_start_date=start_date.isoformat(),
                selected_end_date=end_date.isoformat(),
                range_source="next_week",
            )
            await _ask_template_confirmation(message, state)
            return

        if text == TODAY_LABEL:
            start_date = today_local_date
            await _store_relative_range(state, start_date, "today")
            await _ask_template_confirmation(message, state)
            return

        if text == TOMORROW_LABEL:
            start_date = today_local_date + timedelta(days=1)
            await _store_relative_range(state, start_date, "tomorrow")
            await _ask_template_confirmation(message, state)
            return

        if text == CUSTOM_DATES_LABEL:
            await state.set_state(PlanningStates.custom_start_date)
            await message.answer(
                "Напиши дату начала в формате ДД.ММ.ГГГГ или 2026-03-25.",
                reply_markup=remove_keyboard(),
            )
            return

        await message.answer(
            "Выбери один из готовых вариантов или укажи свои даты.",
        )

    @router.message(PlanningStates.custom_start_date)
    async def handle_custom_start_date(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        state_data = await state.get_data()
        reference_year = date.fromisoformat(cast(str, state_data["today_local_date"])).year
        try:
            start_date = parse_date_input(text, reference_year=reference_year)
        except ValueError as err:
            await message.answer(str(err))
            return

        if start_date < date.fromisoformat(cast(str, state_data["today_local_date"])):
            await message.answer("Нельзя начать план с даты, которая уже прошла.")
            return

        await state.update_data(
            selected_start_date=start_date.isoformat(),
            range_source="custom",
        )
        await state.set_state(PlanningStates.custom_end_date)
        await message.answer(
            "Теперь напиши дату окончания в том же формате.",
            reply_markup=remove_keyboard(),
        )

    @router.message(PlanningStates.custom_end_date)
    async def handle_custom_end_date(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        state_data = await state.get_data()
        reference_year = date.fromisoformat(cast(str, state_data["today_local_date"])).year
        start_date = date.fromisoformat(cast(str, state_data["selected_start_date"]))
        try:
            end_date = parse_date_input(text, reference_year=reference_year)
        except ValueError as err:
            await message.answer(str(err))
            return

        if end_date < start_date:
            await message.answer("Дата окончания не может быть раньше даты начала.")
            return

        await state.update_data(selected_end_date=end_date.isoformat())
        await _ask_template_confirmation(message, state)

    @router.message(PlanningStates.template_confirm)
    async def handle_template_confirm(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        keep_template = _parse_yes_no(text)
        if keep_template is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        state_data = await state.get_data()
        if keep_template:
            await state.update_data(
                selected_meal_count_per_day=cast(int, state_data["default_meal_count_per_day"]),
                selected_desserts_enabled=cast(bool, state_data["default_desserts_enabled"]),
                used_default_template=True,
            )
            await _ask_week_mood(message, state)
            return

        await state.update_data(used_default_template=False)
        await state.set_state(PlanningStates.meal_count)
        await message.answer(
            "Сколько приемов пищи в день планировать на эту неделю?",
            reply_markup=build_meal_count_keyboard(),
        )

    @router.message(PlanningStates.meal_count)
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

        await state.update_data(selected_meal_count_per_day=meal_count)
        await state.set_state(PlanningStates.desserts_enabled)
        await message.answer(
            "Включать десерты в план на эту неделю?",
            reply_markup=build_yes_no_keyboard(),
        )

    @router.message(PlanningStates.desserts_enabled)
    async def handle_desserts_enabled(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        desserts_enabled = _parse_yes_no(text)
        if desserts_enabled is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        await state.update_data(selected_desserts_enabled=desserts_enabled)
        await _ask_week_mood(message, state)

    @router.message(PlanningStates.week_mood)
    async def handle_week_mood(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        if text == SKIP_LABEL:
            week_mood = None
        elif text in WEEK_MOOD_LABELS:
            week_mood = WEEK_MOOD_LABELS[text]
        else:
            await message.answer("Выбери настроение недели кнопкой или нажми Пропустить.")
            return

        await state.update_data(selected_week_mood=week_mood)
        await state.set_state(PlanningStates.weekly_notes)
        await message.answer(
            (
                "Есть ли пожелания или ограничения именно на эту неделю?\n"
                "Например: хочется попроще, без сахара, побольше рыбы. "
                "Можно пропустить."
            ),
            reply_markup=build_skip_keyboard(),
        )

    @router.message(PlanningStates.weekly_notes)
    async def handle_weekly_notes(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        weekly_notes = None if text == SKIP_LABEL else text
        await state.update_data(selected_weekly_notes=weekly_notes)

        pantry_items_count = cast(int, (await state.get_data())["pantry_items_count"])
        if pantry_items_count == 0:
            await message.answer(
                "Запасы пока пусты, поэтому этот шаг пропускаю.",
                reply_markup=remove_keyboard(),
            )
            await _create_plan_draft(
                message,
                state,
                service,
                generation_service,
                pantry_considered=False,
            )
            return

        await state.set_state(PlanningStates.pantry_considered)
        await message.answer(
            "Учитывать продукты, которые уже есть дома?",
            reply_markup=build_yes_no_keyboard(),
        )

    @router.message(PlanningStates.pantry_considered)
    async def handle_pantry_considered(message: Message, state: FSMContext) -> None:
        text = _require_text(message)
        pantry_considered = _parse_yes_no(text)
        if pantry_considered is None:
            await message.answer("Пожалуйста, выбери Да или Нет.")
            return

        await _create_plan_draft(
            message,
            state,
            service,
            generation_service,
            pantry_considered=pantry_considered,
        )

    return router


async def _ask_template_confirmation(message: Message, state: FSMContext) -> None:
    state_data = await state.get_data()
    await state.set_state(PlanningStates.template_confirm)
    meal_count = cast(int, state_data["default_meal_count_per_day"])
    desserts_enabled = cast(bool, state_data["default_desserts_enabled"])
    await message.answer(
        (f"Оставить текущий шаблон на неделю: {describe_template(meal_count, desserts_enabled)}?"),
        reply_markup=build_yes_no_keyboard(),
    )


async def _store_relative_range(
    state: FSMContext,
    start_date: date,
    range_source: str,
) -> None:
    await state.update_data(
        selected_start_date=start_date.isoformat(),
        selected_end_date=(start_date + timedelta(days=6)).isoformat(),
        range_source=range_source,
    )


async def _ask_week_mood(message: Message, state: FSMContext) -> None:
    await state.set_state(PlanningStates.week_mood)
    await message.answer(
        "Выбери настроение недели. Если уклон не нужен, нажми Пропустить.",
        reply_markup=build_week_mood_keyboard(),
    )


async def _create_plan_draft(
    message: Message,
    state: FSMContext,
    service: PlanningService,
    generation_service: WeeklyPlanGenerationService,
    *,
    pantry_considered: bool,
) -> None:
    state_data = await state.get_data()
    meal_count_per_day = cast(int, state_data["selected_meal_count_per_day"])
    desserts_enabled = cast(bool, state_data["selected_desserts_enabled"])
    week_mood = cast(str | None, state_data.get("selected_week_mood"))
    weekly_notes = cast(str | None, state_data.get("selected_weekly_notes"))
    range_source = cast(str, state_data["range_source"])

    try:
        draft = await service.create_plan_draft(
            _require_telegram_user_id(message),
            PlanDraftInput(
                start_date=date.fromisoformat(cast(str, state_data["selected_start_date"])),
                end_date=date.fromisoformat(cast(str, state_data["selected_end_date"])),
                meal_count_per_day=meal_count_per_day,
                desserts_enabled=desserts_enabled,
                week_mood=week_mood,
                weekly_notes=weekly_notes,
                pantry_considered=pantry_considered,
                context_payload={
                    "source": "telegram_plan_flow",
                    "range_source": range_source,
                    "used_default_template": cast(
                        bool,
                        state_data.get("used_default_template", False),
                    ),
                },
            ),
        )
    except ValueError as err:
        await message.answer(str(err), reply_markup=remove_keyboard())
        return

    await state.clear()
    await message.answer(
        (
            "Принял. Составляю план недели.\n"
            f"Период: {format_date(draft.start_date)} - {format_date(draft.end_date)}.\n"
            "Когда закончу, пришлю готовый черновик сообщением."
        ),
        reply_markup=remove_keyboard(),
    )
    generation_task = asyncio.create_task(
        _generate_week_plan_and_send(
            bot=_require_bot(message),
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            generation_service=generation_service,
            weekly_plan_id=draft.weekly_plan_id,
        ),
    )
    generation_task.add_done_callback(_report_background_task_result)


def describe_template(meal_count_per_day: int, desserts_enabled: bool) -> str:
    dessert_text = " + десерт" if desserts_enabled else ""
    return f"{meal_count_per_day} приема пищи{dessert_text}"


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


async def _store_start_context(
    state: FSMContext,
    context: PlanningStartContext,
) -> None:
    await state.update_data(
        today_local_date=context.today_local_date.isoformat(),
        default_start_date=context.default_start_date.isoformat(),
        default_end_date=context.default_end_date.isoformat(),
        default_meal_count_per_day=context.default_meal_count_per_day,
        default_desserts_enabled=context.default_desserts_enabled,
        pantry_items_count=context.pantry_items_count,
    )


async def _start_range_selection(
    message: Message,
    state: FSMContext,
    *,
    default_start_date: date,
    default_end_date: date,
) -> None:
    await state.set_state(PlanningStates.range_choice)
    await message.answer(
        (
            "Начинаем план недели.\n"
            f"По умолчанию предлагаю период {format_date(default_start_date)}"
            f" - {format_date(default_end_date)}."
        ),
        reply_markup=build_range_choice_keyboard(),
    )
    await message.answer("Выбери, с какого периода строить черновик.")


def _require_telegram_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Telegram user context is required")
    return message.from_user.id


def _require_bot(message: Message) -> Bot:
    if message.bot is None:
        raise ValueError("Telegram bot context is required")
    return message.bot


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


async def _generate_week_plan_and_send(
    *,
    bot: Bot,
    chat_id: int,
    message_thread_id: int | None,
    generation_service: WeeklyPlanGenerationService,
    weekly_plan_id: UUID,
) -> None:
    try:
        async with ChatActionSender.typing(
            bot=bot,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
        ):
            result = await generation_service.generate_for_plan(weekly_plan_id)
        await bot.send_message(
            chat_id=chat_id,
            text=result.rendered_message,
            message_thread_id=message_thread_id,
            reply_markup=build_plan_days_keyboard(
                result.weekly_plan_id,
                result.start_date,
                result.end_date,
                allow_confirm=True,
            ),
        )
        await bot.send_message(
            chat_id=chat_id,
            text="Открыть текущий план позже можно командой /week.",
            message_thread_id=message_thread_id,
            reply_markup=remove_keyboard(),
        )
    except Exception:
        logger.exception("weekly plan generation failed for draft %s", weekly_plan_id)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "Не удалось собрать план недели с первого раза.\n"
                "Черновик сохранен, но генерация не завершилась. "
                "Попробуй еще раз чуть позже."
            ),
            message_thread_id=message_thread_id,
            reply_markup=remove_keyboard(),
        )


def _report_background_task_result(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exception = task.exception()
    if exception is not None:
        logger.exception("weekly plan background task crashed", exc_info=exception)
