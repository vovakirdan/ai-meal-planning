from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.reminders.dto import StoredReminderSchedule


class ReminderRepository(Protocol):
    async def list_users_with_enabled_reminders(self) -> list[StoredReminderSchedule]: ...


ReminderRepositoryFactory = Callable[[AsyncSession], ReminderRepository]
