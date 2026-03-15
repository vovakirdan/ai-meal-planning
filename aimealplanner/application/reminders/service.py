# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.dto import PlanningStartContext
from aimealplanner.application.planning.feedback_dto import ReviewStartContext
from aimealplanner.application.reminders.dto import ReminderDispatch, StoredReminderSchedule
from aimealplanner.application.reminders.repositories import ReminderRepositoryFactory


class ReviewReminderService(Protocol):
    async def start_review(self, telegram_user_id: int) -> ReviewStartContext: ...


class PlanningReminderService(Protocol):
    async def start_planning(self, telegram_user_id: int) -> PlanningStartContext: ...


@dataclass(slots=True)
class ReminderService:
    session_factory: async_sessionmaker[AsyncSession]
    repositories_factory: ReminderRepositoryFactory
    review_service: ReviewReminderService
    planning_service: PlanningReminderService

    async def collect_due_dispatches(self, now_utc: datetime) -> list[ReminderDispatch]:
        resolved_now = _normalize_utc(now_utc)
        async with self.session_factory() as session:
            schedules = await self.repositories_factory(session).list_users_with_enabled_reminders()

        dispatches: list[ReminderDispatch] = []
        for schedule in schedules:
            local_now = resolved_now.astimezone(_resolve_timezone(schedule.timezone))
            local_today = local_now.date()

            if _is_daily_review_due(schedule, local_now):
                dispatch = await self._build_daily_review_dispatch(schedule, local_today)
                if dispatch is not None:
                    dispatches.append(dispatch)

            if _is_weekly_planning_due(schedule, local_now):
                dispatch = await self._build_weekly_planning_dispatch(schedule, local_today)
                if dispatch is not None:
                    dispatches.append(dispatch)

        return dispatches

    async def _build_daily_review_dispatch(
        self,
        schedule: StoredReminderSchedule,
        local_today: date,
    ) -> ReminderDispatch | None:
        try:
            review_context = await self.review_service.start_review(schedule.telegram_user_id)
        except ValueError:
            return None

        matching_day = next(
            (day for day in review_context.days if day.meal_date == local_today),
            None,
        )
        if matching_day is None:
            return None

        return ReminderDispatch(
            kind="daily_review",
            telegram_user_id=schedule.telegram_user_id,
            local_date=local_today,
            dedupe_key=f"reminder:daily_review:{schedule.telegram_user_id}:{local_today.isoformat()}",
            text=(
                "Пора оценить блюда за сегодня.\n"
                f"{_render_local_date(local_today)} · "
                f"{matching_day.items_count} {_render_items_label(matching_day.items_count)}.\n"
                "Открой /review, чтобы быстро пройтись по оценкам."
            ),
        )

    async def _build_weekly_planning_dispatch(
        self,
        schedule: StoredReminderSchedule,
        local_today: date,
    ) -> ReminderDispatch | None:
        try:
            planning_context = await self.planning_service.start_planning(
                schedule.telegram_user_id,
            )
        except ValueError:
            return None

        if planning_context.existing_draft is not None:
            text = (
                "Пора вернуться к недельному меню.\n"
                "У тебя уже есть черновик на период "
                f"{planning_context.existing_draft.start_date.strftime('%d.%m.%Y')} - "
                f"{planning_context.existing_draft.end_date.strftime('%d.%m.%Y')}.\n"
                "Продолжить можно через /plan."
            )
        else:
            text = (
                "Пора составить план на следующую неделю.\n"
                "По умолчанию предложу период "
                f"{planning_context.default_start_date.strftime('%d.%m.%Y')} - "
                f"{planning_context.default_end_date.strftime('%d.%m.%Y')}.\n"
                "Открой /plan."
            )

        return ReminderDispatch(
            kind="weekly_planning",
            telegram_user_id=schedule.telegram_user_id,
            local_date=local_today,
            dedupe_key=f"reminder:weekly_planning:{schedule.telegram_user_id}:{local_today.isoformat()}",
            text=text,
        )


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def _is_daily_review_due(schedule: StoredReminderSchedule, local_now: datetime) -> bool:
    if (
        not schedule.daily_feedback_reminder_enabled
        or schedule.daily_feedback_reminder_time is None
    ):
        return False
    return _matches_minute(local_now, schedule.daily_feedback_reminder_time)


def _is_weekly_planning_due(schedule: StoredReminderSchedule, local_now: datetime) -> bool:
    if (
        not schedule.weekly_planning_reminder_enabled
        or schedule.weekly_planning_reminder_day_of_week is None
        or schedule.weekly_planning_reminder_time is None
    ):
        return False
    if local_now.weekday() != schedule.weekly_planning_reminder_day_of_week:
        return False
    return _matches_minute(local_now, schedule.weekly_planning_reminder_time)


def _matches_minute(local_now: datetime, reminder_time: time) -> bool:
    return local_now.hour == reminder_time.hour and local_now.minute == reminder_time.minute


def _render_local_date(value: date) -> str:
    weekdays = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return f"{value.strftime('%d.%m.%Y')} ({weekdays[value.weekday()]})"


def _render_items_label(items_count: int) -> str:
    if items_count % 10 == 1 and items_count % 100 != 11:
        return "блюдо"
    if items_count % 10 in {2, 3, 4} and items_count % 100 not in {12, 13, 14}:
        return "блюда"
    return "блюд"
