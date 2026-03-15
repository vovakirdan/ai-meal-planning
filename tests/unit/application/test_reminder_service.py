from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import cast
from uuid import uuid4

import pytest
from aimealplanner.application.planning.dto import (
    PlanningStartContext,
    StoredDraftPlan,
)
from aimealplanner.application.planning.feedback_dto import ReviewDayOption, ReviewStartContext
from aimealplanner.application.reminders.dto import StoredReminderSchedule
from aimealplanner.application.reminders.repositories import (
    ReminderRepository,
    ReminderRepositoryFactory,
)
from aimealplanner.application.reminders.service import ReminderService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class FakeSession:
    pass


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeSession:
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def __call__(self) -> FakeSessionContext:
        return FakeSessionContext(self._session)


@dataclass
class FakeReminderRepository:
    schedules: list[StoredReminderSchedule]

    async def list_users_with_enabled_reminders(self) -> list[StoredReminderSchedule]:
        return self.schedules


@dataclass
class FakeReviewService:
    contexts_by_user_id: dict[int, ReviewStartContext] = field(default_factory=dict)

    async def start_review(self, telegram_user_id: int) -> ReviewStartContext:
        if telegram_user_id not in self.contexts_by_user_id:
            raise ValueError("no review")
        return self.contexts_by_user_id[telegram_user_id]


@dataclass
class FakePlanningService:
    contexts_by_user_id: dict[int, PlanningStartContext] = field(default_factory=dict)

    async def start_planning(self, telegram_user_id: int) -> PlanningStartContext:
        if telegram_user_id not in self.contexts_by_user_id:
            raise ValueError("no planning")
        return self.contexts_by_user_id[telegram_user_id]


def _build_service(
    *,
    schedules: list[StoredReminderSchedule],
    review_service: FakeReviewService | None = None,
    planning_service: FakePlanningService | None = None,
) -> ReminderService:
    repository = FakeReminderRepository(schedules=schedules)
    return ReminderService(
        session_factory=cast(async_sessionmaker[AsyncSession], FakeSessionFactory(FakeSession())),
        repositories_factory=cast(
            ReminderRepositoryFactory,
            lambda _session: cast(ReminderRepository, repository),
        ),
        review_service=review_service or FakeReviewService(),
        planning_service=planning_service or FakePlanningService(),
    )


def _build_schedule(
    *,
    telegram_user_id: int = 101,
    timezone: str = "Europe/Moscow",
    daily_enabled: bool = True,
    daily_time: time | None = time(hour=20, minute=30),
    weekly_enabled: bool = True,
    weekly_day: int | None = 6,
    weekly_time: time | None = time(hour=11, minute=0),
) -> StoredReminderSchedule:
    return StoredReminderSchedule(
        user_id=uuid4(),
        telegram_user_id=telegram_user_id,
        timezone=timezone,
        daily_feedback_reminder_enabled=daily_enabled,
        daily_feedback_reminder_time=daily_time,
        weekly_planning_reminder_enabled=weekly_enabled,
        weekly_planning_reminder_day_of_week=weekly_day,
        weekly_planning_reminder_time=weekly_time,
    )


@pytest.mark.asyncio
async def test_collect_due_dispatches_returns_daily_review_for_today() -> None:
    local_today = date(2026, 3, 15)
    service = _build_service(
        schedules=[_build_schedule(daily_time=time(hour=20, minute=30), weekly_enabled=False)],
        review_service=FakeReviewService(
            contexts_by_user_id={
                101: ReviewStartContext(
                    weekly_plan_id=uuid4(),
                    start_date=local_today,
                    end_date=local_today,
                    days=[
                        ReviewDayOption(
                            meal_date=local_today,
                            meals_count=3,
                            items_count=6,
                        ),
                    ],
                ),
            },
        ),
    )

    dispatches = await service.collect_due_dispatches(
        datetime(2026, 3, 15, 17, 30, tzinfo=UTC),
    )

    assert len(dispatches) == 1
    dispatch = dispatches[0]
    assert dispatch.kind == "daily_review"
    assert dispatch.telegram_user_id == 101
    assert dispatch.local_date == local_today
    assert "/review" in dispatch.text


@pytest.mark.asyncio
async def test_collect_due_dispatches_skips_daily_review_without_today_plan() -> None:
    service = _build_service(
        schedules=[_build_schedule(weekly_enabled=False)],
        review_service=FakeReviewService(
            contexts_by_user_id={
                101: ReviewStartContext(
                    weekly_plan_id=uuid4(),
                    start_date=date(2026, 3, 10),
                    end_date=date(2026, 3, 16),
                    days=[
                        ReviewDayOption(
                            meal_date=date(2026, 3, 14),
                            meals_count=2,
                            items_count=4,
                        ),
                    ],
                ),
            },
        ),
    )

    dispatches = await service.collect_due_dispatches(
        datetime(2026, 3, 15, 17, 30, tzinfo=UTC),
    )

    assert dispatches == []


@pytest.mark.asyncio
async def test_collect_due_dispatches_returns_weekly_reminder_with_existing_draft() -> None:
    local_today = date(2026, 3, 15)
    service = _build_service(
        schedules=[
            _build_schedule(
                daily_enabled=False,
                weekly_enabled=True,
                weekly_day=6,
                weekly_time=time(hour=11, minute=0),
            ),
        ],
        planning_service=FakePlanningService(
            contexts_by_user_id={
                101: PlanningStartContext(
                    timezone="Europe/Moscow",
                    today_local_date=local_today,
                    default_start_date=date(2026, 3, 16),
                    default_end_date=date(2026, 3, 22),
                    default_meal_count_per_day=3,
                    default_desserts_enabled=False,
                    pantry_items_count=2,
                    existing_draft=StoredDraftPlan(
                        id=uuid4(),
                        start_date=date(2026, 3, 16),
                        end_date=date(2026, 3, 22),
                    ),
                ),
            },
        ),
    )

    dispatches = await service.collect_due_dispatches(
        datetime(2026, 3, 15, 8, 0, tzinfo=UTC),
    )

    assert len(dispatches) == 1
    dispatch = dispatches[0]
    assert dispatch.kind == "weekly_planning"
    assert "/plan" in dispatch.text
    assert "уже есть черновик" in dispatch.text.lower()


@pytest.mark.asyncio
async def test_collect_due_dispatches_respects_timezone_and_minute() -> None:
    service = _build_service(
        schedules=[
            _build_schedule(
                timezone="Europe/Moscow",
                daily_time=time(hour=20, minute=30),
                weekly_enabled=False,
            ),
        ],
        review_service=FakeReviewService(
            contexts_by_user_id={
                101: ReviewStartContext(
                    weekly_plan_id=uuid4(),
                    start_date=date(2026, 3, 15),
                    end_date=date(2026, 3, 15),
                    days=[
                        ReviewDayOption(
                            meal_date=date(2026, 3, 15),
                            meals_count=1,
                            items_count=1,
                        ),
                    ],
                ),
            },
        ),
    )

    wrong_minute = await service.collect_due_dispatches(
        datetime(2026, 3, 15, 17, 29, tzinfo=UTC),
    )
    correct_minute = await service.collect_due_dispatches(
        datetime(2026, 3, 15, 17, 30, tzinfo=UTC),
    )

    assert wrong_minute == []
    assert len(correct_minute) == 1
