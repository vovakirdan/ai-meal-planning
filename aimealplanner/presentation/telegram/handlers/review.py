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

from aimealplanner.application.planning import (
    DishReviewService,
    ReviewQueueEntry,
    ReviewStartContext,
)
from aimealplanner.infrastructure.ai import OpenAIWeeklyPlanGenerator
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict
from aimealplanner.infrastructure.db.repositories import build_planning_repositories
from aimealplanner.presentation.telegram.keyboards.onboarding import (
    CANCEL_LABEL,
    remove_keyboard,
)
from aimealplanner.presentation.telegram.keyboards.review import (
    build_review_comment_keyboard,
    build_review_days_keyboard,
    build_review_negative_keyboard,
    build_review_verdict_keyboard,
    parse_review_day_callback,
    parse_review_negative_callback,
    parse_review_verdict_callback,
)
from aimealplanner.presentation.telegram.states.review import ReviewStates


def build_review_router(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    weekly_plan_generator: OpenAIWeeklyPlanGenerator,
) -> Router:
    router = Router(name="review")
    review_service = DishReviewService(
        session_factory,
        build_planning_repositories,
        comment_client=weekly_plan_generator,
    )

    @router.message(Command("review"))
    async def handle_review_command(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            context = await review_service.start_review(
                _require_telegram_user_id_from_message(message),
            )
        except ValueError as err:
            await message.answer(str(err), reply_markup=remove_keyboard())
            return

        await message.answer(
            _render_review_start(context),
            reply_markup=build_review_days_keyboard(
                context.weekly_plan_id,
                [
                    (
                        day.meal_date,
                        (
                            f"{_format_day_label(day.meal_date)} · "
                            f"{day.items_count} {_render_item_count_label(day.items_count)}"
                        ),
                    )
                    for day in context.days
                ],
            ),
        )

    @router.callback_query(F.data.startswith("rwd:"))
    async def handle_review_day_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        callback_data = cast(str, callback.data)
        parsed_value = parse_review_day_callback(callback_data)
        if parsed_value is None:
            await callback.answer("Не получилось открыть выбранный день.", show_alert=True)
            return

        weekly_plan_id, meal_date = parsed_value
        try:
            day_session = await review_service.start_day_review(
                _require_telegram_user_id_from_callback(callback),
                weekly_plan_id=weekly_plan_id,
                meal_date=meal_date,
            )
        except ValueError as err:
            await callback.answer(str(err), show_alert=True)
            return

        callback_message = _require_callback_message(callback)
        await state.set_state(ReviewStates.active)
        await state.update_data(
            review_queue=[_serialize_review_entry(entry) for entry in day_session.entries],
            review_index=0,
            review_message_id=callback_message.message_id,
            review_chat_id=callback_message.chat.id,
            review_meal_date=day_session.meal_date.isoformat(),
            review_pending_verdict=None,
        )

        first_entry = day_session.entries[0]
        await _edit_callback_message(
            callback,
            text=_render_review_entry(
                first_entry,
                position=1,
                total=len(day_session.entries),
            ),
            reply_markup=build_review_verdict_keyboard(),
        )

    @router.callback_query(F.data.startswith("rwv:"))
    async def handle_review_verdict_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        callback_data = cast(str, callback.data)
        verdict = parse_review_verdict_callback(callback_data)
        if verdict is None:
            await callback.answer("Не получилось сохранить оценку.", show_alert=True)
            return

        entry = await _get_current_review_entry(state)
        if entry is None:
            await callback.answer("Сценарий устарел. Открой /review заново.", show_alert=True)
            return

        current_index, total = await _get_review_progress(state)
        if verdict in {DishFeedbackVerdict.RARELY_REPEAT, DishFeedbackVerdict.NEVER_AGAIN}:
            await state.set_state(ReviewStates.active)
            await state.update_data(review_pending_verdict=verdict.value)
            await _edit_callback_message(
                callback,
                text=_render_negative_review_entry(
                    entry,
                    position=current_index + 1,
                    total=total,
                ),
                reply_markup=build_review_negative_keyboard(),
            )
            return

        await _save_feedback_and_advance(
            bot=_require_callback_bot(callback),
            state=state,
            review_service=review_service,
            telegram_user_id=_require_telegram_user_id_from_callback(callback),
            entry=entry,
            verdict=verdict,
            raw_comment=None,
        )
        await callback.answer(_render_verdict_toast(verdict))

    @router.callback_query(F.data.startswith("rwn:"))
    async def handle_review_negative_callback(
        callback: CallbackQuery,
        state: FSMContext,
    ) -> None:
        action = parse_review_negative_callback(cast(str, callback.data))
        if action is None:
            await callback.answer("Не получилось продолжить оценку.", show_alert=True)
            return

        entry = await _get_current_review_entry(state)
        verdict = await _get_pending_verdict(state)
        if entry is None or verdict is None:
            await callback.answer("Сценарий устарел. Открой /review заново.", show_alert=True)
            return

        current_index, total = await _get_review_progress(state)
        if action == "comment":
            await state.set_state(ReviewStates.comment)
            await _edit_callback_message(
                callback,
                text=_render_comment_request(
                    entry,
                    position=current_index + 1,
                    total=total,
                ),
                reply_markup=build_review_comment_keyboard(),
            )
            return

        await _save_feedback_and_advance(
            bot=_require_callback_bot(callback),
            state=state,
            review_service=review_service,
            telegram_user_id=_require_telegram_user_id_from_callback(callback),
            entry=entry,
            verdict=verdict,
            raw_comment=None,
        )
        await callback.answer("Сохранил.")

    @router.message(ReviewStates.comment)
    async def handle_review_comment(message: Message, state: FSMContext) -> None:
        try:
            raw_text = _require_text(message)
        except ValueError:
            await message.answer("Напиши комментарий обычным текстом или нажми «Пропустить».")
            return

        if raw_text in {"/cancel", CANCEL_LABEL}:
            state_data = await state.get_data()
            await state.clear()
            await _edit_review_message(
                bot=_require_message_bot(message),
                state_data=state_data,
                text="Сбор отзывов остановлен. Вернуться можно через /review.",
                reply_markup=None,
            )
            return

        entry = await _get_current_review_entry(state)
        verdict = await _get_pending_verdict(state)
        if entry is None or verdict is None:
            state_data = await state.get_data()
            await state.clear()
            await _edit_review_message(
                bot=_require_message_bot(message),
                state_data=state_data,
                text="Не удалось восстановить шаг отзыва. Открой /review заново.",
                reply_markup=None,
            )
            return

        async with ChatActionSender.typing(
            bot=_require_message_bot(message),
            chat_id=message.chat.id,
        ):
            await _save_feedback_and_advance(
                bot=_require_message_bot(message),
                state=state,
                review_service=review_service,
                telegram_user_id=_require_telegram_user_id_from_message(message),
                entry=entry,
                verdict=verdict,
                raw_comment=raw_text,
            )

    return router


async def _save_feedback_and_advance(
    *,
    bot: Bot,
    state: FSMContext,
    review_service: DishReviewService,
    telegram_user_id: int,
    entry: ReviewQueueEntry,
    verdict: DishFeedbackVerdict,
    raw_comment: str | None,
) -> None:
    await review_service.save_feedback(
        telegram_user_id,
        entry=entry,
        verdict=verdict,
        raw_comment=raw_comment,
    )

    state_data = await state.get_data()
    queue = _deserialize_review_queue(state_data)
    current_index = cast(int, state_data.get("review_index", 0))
    next_index = current_index + 1

    if next_index >= len(queue):
        await state.clear()
        await _edit_review_message(
            bot=bot,
            state_data=state_data,
            text=_render_review_complete(entry.meal_date, len(queue)),
            reply_markup=None,
        )
        return

    next_entry = queue[next_index]
    await state.set_state(ReviewStates.active)
    await state.update_data(
        review_index=next_index,
        review_pending_verdict=None,
    )
    await _edit_review_message(
        bot=bot,
        state_data=state_data,
        text=_render_review_entry(
            next_entry,
            position=next_index + 1,
            total=len(queue),
        ),
        reply_markup=build_review_verdict_keyboard(),
    )


async def _edit_callback_message(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    message = _require_callback_message(callback)
    await message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()


async def _edit_review_message(
    *,
    bot: Bot,
    state_data: dict[str, Any],
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    message_id = cast(int | None, state_data.get("review_message_id"))
    chat_id = cast(int | None, state_data.get("review_chat_id"))
    if message_id is None or chat_id is None:
        return
    await bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )


async def _get_current_review_entry(state: FSMContext) -> ReviewQueueEntry | None:
    state_data = await state.get_data()
    queue = _deserialize_review_queue(state_data)
    current_index = cast(int, state_data.get("review_index", 0))
    if current_index < 0 or current_index >= len(queue):
        return None
    return queue[current_index]


async def _get_review_progress(state: FSMContext) -> tuple[int, int]:
    state_data = await state.get_data()
    queue = _deserialize_review_queue(state_data)
    current_index = cast(int, state_data.get("review_index", 0))
    return current_index, len(queue)


async def _get_pending_verdict(state: FSMContext) -> DishFeedbackVerdict | None:
    state_data = await state.get_data()
    verdict_value = cast(str | None, state_data.get("review_pending_verdict"))
    if verdict_value is None:
        return None
    try:
        return DishFeedbackVerdict(verdict_value)
    except ValueError:
        return None


def _deserialize_review_queue(state_data: dict[str, Any]) -> list[ReviewQueueEntry]:
    raw_queue = cast(list[dict[str, str]], state_data.get("review_queue", []))
    return [
        ReviewQueueEntry(
            planned_meal_item_id=UUID(hex=entry["planned_meal_item_id"]),
            meal_date=date.fromisoformat(entry["meal_date"]),
            slot=entry["slot"],
            dish_name=entry["dish_name"],
            household_member_id=UUID(hex=entry["household_member_id"]),
            household_member_name=entry["household_member_name"],
        )
        for entry in raw_queue
    ]


def _serialize_review_entry(entry: ReviewQueueEntry) -> dict[str, str]:
    return {
        "planned_meal_item_id": entry.planned_meal_item_id.hex,
        "meal_date": entry.meal_date.isoformat(),
        "slot": entry.slot,
        "dish_name": entry.dish_name,
        "household_member_id": entry.household_member_id.hex,
        "household_member_name": entry.household_member_name,
    }


def _render_review_start(context: ReviewStartContext) -> str:
    return (
        "Давай оценим блюда из подтвержденной недели.\n"
        f"Период: {context.start_date.strftime('%d.%m.%Y')} - "
        f"{context.end_date.strftime('%d.%m.%Y')}.\n\n"
        "Выбери день, за который хочешь оставить отзывы."
    )


def _render_review_entry(entry: ReviewQueueEntry, *, position: int, total: int) -> str:
    return (
        f"Оценка {position} из {total}\n\n"
        f"Блюдо: {entry.dish_name}\n"
        f"Когда: {entry.meal_date.strftime('%d.%m.%Y')} ({_weekday_name(entry.meal_date)}) · "
        f"{_render_slot_name(entry.slot)}\n"
        f"Для кого: {entry.household_member_name}\n\n"
        "Как оценить это блюдо?"
    )


def _render_negative_review_entry(
    entry: ReviewQueueEntry,
    *,
    position: int,
    total: int,
) -> str:
    return (
        f"Оценка {position} из {total}\n\n"
        f"Блюдо: {entry.dish_name}\n"
        f"Когда: {entry.meal_date.strftime('%d.%m.%Y')} ({_weekday_name(entry.meal_date)}) · "
        f"{_render_slot_name(entry.slot)}\n"
        f"Для кого: {entry.household_member_name}\n\n"
        "Понял, блюдо не зашло.\n"
        "Хочешь оставить комментарий или пропустим?"
    )


def _render_comment_request(
    entry: ReviewQueueEntry,
    *,
    position: int,
    total: int,
) -> str:
    return (
        f"Оценка {position} из {total}\n\n"
        f"Блюдо: {entry.dish_name}\n"
        f"Когда: {entry.meal_date.strftime('%d.%m.%Y')} ({_weekday_name(entry.meal_date)}) · "
        f"{_render_slot_name(entry.slot)}\n"
        f"Для кого: {entry.household_member_name}\n\n"
        "Напиши одним сообщением, что именно не зашло.\n"
        "Например: слишком жирно, слишком остро, хочется мягче вкус.\n"
        "Или нажми «Пропустить»."
    )


def _render_review_complete(meal_date: date, total: int) -> str:
    return (
        f"Отзывы за {meal_date.strftime('%d.%m.%Y')} сохранены.\n\n"
        f"Всего оценок: {total}.\n"
        "Если захочешь оценить другой день, снова отправь /review."
    )


def _render_verdict_toast(verdict: DishFeedbackVerdict) -> str:
    if verdict is DishFeedbackVerdict.FAVORITE:
        return "Запомнил как любимое."
    if verdict is DishFeedbackVerdict.CAN_REPEAT:
        return "Запомнил, что блюдо норм."
    return "Сохранил."


def _format_day_label(value: date) -> str:
    return f"{value.strftime('%d.%m.%Y')} ({_weekday_name(value)})"


def _render_item_count_label(count: int) -> str:
    remainder_10 = count % 10
    remainder_100 = count % 100
    if remainder_10 == 1 and remainder_100 != 11:
        return "блюдо"
    if remainder_10 in {2, 3, 4} and remainder_100 not in {12, 13, 14}:
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


def _require_callback_message(callback: CallbackQuery) -> Message:
    if callback.message is None or not isinstance(callback.message, Message):
        raise ValueError("Callback message is not available")
    return callback.message


def _require_text(message: Message) -> str:
    if message.text is None:
        raise ValueError("text message required")
    text = message.text.strip()
    if not text:
        raise ValueError("text message required")
    return text


def _require_telegram_user_id_from_message(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Не удалось определить пользователя Telegram.")
    return message.from_user.id


def _require_telegram_user_id_from_callback(callback: CallbackQuery) -> int:
    if callback.from_user is None:
        raise ValueError("Не удалось определить пользователя Telegram.")
    return callback.from_user.id


def _require_message_bot(message: Message) -> Bot:
    return cast(Bot, message.bot)


def _require_callback_bot(callback: CallbackQuery) -> Bot:
    return cast(Bot, _require_callback_message(callback).bot)
