from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.household import HouseholdRecord


class UserRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "ix_users_daily_feedback_reminder_schedule",
            "daily_feedback_reminder_enabled",
            "daily_feedback_reminder_time",
        ),
        Index(
            "ix_users_weekly_planning_reminder_schedule",
            "weekly_planning_reminder_enabled",
            "weekly_planning_reminder_day_of_week",
            "weekly_planning_reminder_time",
        ),
        UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        CheckConstraint(
            "weekly_planning_reminder_day_of_week BETWEEN 0 AND 6",
            name="weekly_planning_reminder_day_of_week_range",
        ),
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Moscow")
    daily_feedback_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    daily_feedback_reminder_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    weekly_planning_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    weekly_planning_reminder_day_of_week: Mapped[int | None] = mapped_column(SmallInteger)
    weekly_planning_reminder_time: Mapped[time | None] = mapped_column(Time(timezone=False))

    household: Mapped[HouseholdRecord | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
