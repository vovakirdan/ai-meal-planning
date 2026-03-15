from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Literal
from uuid import UUID

ReminderKind = Literal["daily_review", "weekly_planning"]


@dataclass(frozen=True, slots=True)
class StoredReminderSchedule:
    user_id: UUID
    telegram_user_id: int
    timezone: str
    daily_feedback_reminder_enabled: bool
    daily_feedback_reminder_time: time | None
    weekly_planning_reminder_enabled: bool
    weekly_planning_reminder_day_of_week: int | None
    weekly_planning_reminder_time: time | None


@dataclass(frozen=True, slots=True)
class ReminderDispatch:
    kind: ReminderKind
    telegram_user_id: int
    local_date: date
    dedupe_key: str
    text: str
