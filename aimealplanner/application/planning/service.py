from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.dto import (
    PlanConfirmationResult,
    PlanDraftInput,
    PlanDraftResult,
    PlanningStartContext,
    StoredPlanningHousehold,
)
from aimealplanner.application.planning.repositories import (
    PlanningRepositoryBundleFactory,
)
from aimealplanner.infrastructure.db.enums import MealSlot


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True)
class MealTemplate:
    meal_count_per_day: int
    desserts_enabled: bool
    active_slots: list[str]


class PlanningService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._clock = clock

    async def start_planning(self, telegram_user_id: int) -> PlanningStartContext:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("Профиль не найден. Сначала отправь /start.")

            household = await repositories.household_repository.get_by_user_id(user.id)
            if household is None or household.onboarding_completed_at is None:
                raise ValueError("Сначала заверши стартовую настройку через /start.")

            local_today = self._clock().astimezone(_resolve_timezone(user.timezone)).date()
            default_start_date, default_end_date = _build_default_range(local_today)
            existing_draft = (
                await repositories.weekly_plan_repository.get_latest_draft_for_household(
                    household.id,
                )
            )
            return PlanningStartContext(
                timezone=user.timezone,
                today_local_date=local_today,
                default_start_date=default_start_date,
                default_end_date=default_end_date,
                default_meal_count_per_day=household.default_meal_count_per_day,
                default_desserts_enabled=household.desserts_enabled,
                pantry_items_count=household.pantry_items_count,
                existing_draft=existing_draft,
            )

    async def discard_existing_drafts(self, telegram_user_id: int) -> int:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("Профиль не найден. Сначала отправь /start.")

            household = await repositories.household_repository.get_by_user_id(user.id)
            if household is None or household.onboarding_completed_at is None:
                raise ValueError("Сначала заверши стартовую настройку через /start.")

            deleted_count = await repositories.weekly_plan_repository.delete_drafts_for_household(
                household.id,
            )
            await session.commit()
            return deleted_count

    async def create_plan_draft(
        self,
        telegram_user_id: int,
        draft: PlanDraftInput,
    ) -> PlanDraftResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("Профиль не найден. Сначала отправь /start.")

            household = await repositories.household_repository.get_by_user_id(user.id)
            if household is None or household.onboarding_completed_at is None:
                raise ValueError("Сначала заверши стартовую настройку через /start.")

            local_today = self._clock().astimezone(_resolve_timezone(user.timezone)).date()
            _validate_draft_input(
                draft,
                household,
                today_local_date=local_today,
            )
            active_slots = build_active_slots(
                draft.meal_count_per_day,
                draft.desserts_enabled,
            )
            plan = await repositories.weekly_plan_repository.create_draft(
                household.id,
                user.timezone,
                active_slots,
                draft,
            )
            await session.commit()
            return plan

    async def confirm_plan(
        self,
        telegram_user_id: int,
        weekly_plan_id: UUID,
    ) -> PlanConfirmationResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("Профиль не найден. Сначала отправь /start.")

            household = await repositories.household_repository.get_by_user_id(user.id)
            if household is None or household.onboarding_completed_at is None:
                raise ValueError("Сначала заверши стартовую настройку через /start.")

            result = await repositories.weekly_plan_repository.confirm_plan(
                household.id,
                weekly_plan_id,
                confirmed_at=self._clock(),
            )
            await session.commit()
            return result


def _validate_draft_input(
    draft: PlanDraftInput,
    household: StoredPlanningHousehold,
    *,
    today_local_date: date,
) -> None:
    if draft.start_date > draft.end_date:
        raise ValueError("Дата окончания не может быть раньше даты начала.")
    if draft.start_date < today_local_date:
        raise ValueError("Нельзя начать план с даты, которая уже прошла.")
    if draft.meal_count_per_day not in range(2, 6):
        raise ValueError("Количество приемов пищи должно быть от 2 до 5.")
    if draft.pantry_considered and household.pantry_items_count == 0:
        raise ValueError("Нечего учитывать в запасах: они пока не заполнены.")


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def _build_default_range(today_local_date: date) -> tuple[date, date]:
    start_date = today_local_date
    if today_local_date.weekday() != 0:
        days_until_next_monday = 7 - today_local_date.weekday()
        start_date = today_local_date + timedelta(days=days_until_next_monday)
    end_date = start_date + timedelta(days=6)
    return start_date, end_date


def build_active_slots(meal_count_per_day: int, desserts_enabled: bool) -> list[str]:
    slots_by_count = {
        2: [MealSlot.BREAKFAST, MealSlot.DINNER],
        3: [MealSlot.BREAKFAST, MealSlot.LUNCH, MealSlot.DINNER],
        4: [MealSlot.BREAKFAST, MealSlot.LUNCH, MealSlot.DINNER, MealSlot.SNACK_1],
        5: [
            MealSlot.BREAKFAST,
            MealSlot.LUNCH,
            MealSlot.DINNER,
            MealSlot.SNACK_1,
            MealSlot.SNACK_2,
        ],
    }
    if meal_count_per_day not in slots_by_count:
        raise ValueError(f"Unsupported meal count: {meal_count_per_day}")

    active_slots = [slot.value for slot in slots_by_count[meal_count_per_day]]
    if desserts_enabled:
        active_slots.append(MealSlot.DESSERT.value)
    return active_slots
