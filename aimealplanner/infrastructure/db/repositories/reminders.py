from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.reminders.dto import StoredReminderSchedule
from aimealplanner.infrastructure.db.models.household import HouseholdRecord
from aimealplanner.infrastructure.db.models.user import UserRecord


class SqlAlchemyReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_users_with_enabled_reminders(self) -> list[StoredReminderSchedule]:
        statement = (
            select(UserRecord)
            .join(HouseholdRecord, HouseholdRecord.user_id == UserRecord.id)
            .where(
                HouseholdRecord.onboarding_completed_at.is_not(None),
                or_(
                    UserRecord.daily_feedback_reminder_enabled.is_(True),
                    UserRecord.weekly_planning_reminder_enabled.is_(True),
                ),
            )
            .order_by(UserRecord.id.asc())
        )
        users = list(await self._session.scalars(statement))
        return [
            StoredReminderSchedule(
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
                timezone=user.timezone,
                daily_feedback_reminder_enabled=user.daily_feedback_reminder_enabled,
                daily_feedback_reminder_time=user.daily_feedback_reminder_time,
                weekly_planning_reminder_enabled=user.weekly_planning_reminder_enabled,
                weekly_planning_reminder_day_of_week=user.weekly_planning_reminder_day_of_week,
                weekly_planning_reminder_time=user.weekly_planning_reminder_time,
            )
            for user in users
        ]


def build_reminder_repository(session: AsyncSession) -> SqlAlchemyReminderRepository:
    return SqlAlchemyReminderRepository(session)
