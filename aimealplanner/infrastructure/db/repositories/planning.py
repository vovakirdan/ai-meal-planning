from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aimealplanner.application.planning.dto import (
    PlanDraftInput,
    PlanDraftResult,
    StoredDraftPlan,
    StoredPlanningHousehold,
    StoredPlanningUser,
)
from aimealplanner.application.planning.repositories import PlanningRepositories
from aimealplanner.infrastructure.db.enums import WeeklyPlanStatus
from aimealplanner.infrastructure.db.models.household import HouseholdRecord, PantryItemRecord
from aimealplanner.infrastructure.db.models.plan import WeeklyPlanRecord
from aimealplanner.infrastructure.db.models.user import UserRecord


class SqlAlchemyPlanningUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> StoredPlanningUser | None:
        statement = select(UserRecord).where(UserRecord.telegram_user_id == telegram_user_id)
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return StoredPlanningUser(
            id=record.id,
            telegram_user_id=record.telegram_user_id,
            timezone=record.timezone,
        )


class SqlAlchemyPlanningHouseholdRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> StoredPlanningHousehold | None:
        household_statement = select(HouseholdRecord).where(HouseholdRecord.user_id == user_id)
        household = await self._session.scalar(household_statement)
        if household is None:
            return None

        pantry_count_statement = select(func.count(PantryItemRecord.id)).where(
            PantryItemRecord.household_id == household.id,
        )
        pantry_items_count = await self._session.scalar(pantry_count_statement)
        return StoredPlanningHousehold(
            id=household.id,
            user_id=household.user_id,
            onboarding_completed_at=household.onboarding_completed_at,
            default_meal_count_per_day=household.default_meal_count_per_day,
            desserts_enabled=household.desserts_enabled,
            pantry_items_count=pantry_items_count or 0,
        )


class SqlAlchemyWeeklyPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_draft_for_household(self, household_id: UUID) -> StoredDraftPlan | None:
        statement = (
            select(WeeklyPlanRecord)
            .where(
                WeeklyPlanRecord.household_id == household_id,
                WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
            )
            .order_by(WeeklyPlanRecord.created_at.desc())
            .limit(1)
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return StoredDraftPlan(
            id=record.id,
            start_date=record.start_date,
            end_date=record.end_date,
        )

    async def delete_drafts_for_household(self, household_id: UUID) -> int:
        count_statement = select(func.count(WeeklyPlanRecord.id)).where(
            WeeklyPlanRecord.household_id == household_id,
            WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
        )
        existing_draft_count = await self._session.scalar(count_statement)
        delete_statement = delete(WeeklyPlanRecord).where(
            WeeklyPlanRecord.household_id == household_id,
            WeeklyPlanRecord.status == WeeklyPlanStatus.DRAFT,
        )
        await self._session.execute(delete_statement)
        return existing_draft_count or 0

    async def create_draft(
        self,
        household_id: UUID,
        timezone: str,
        active_slots: list[str],
        draft: PlanDraftInput,
    ) -> PlanDraftResult:
        record = WeeklyPlanRecord(
            household_id=household_id,
            start_date=draft.start_date,
            end_date=draft.end_date,
            timezone=timezone,
            meal_count_per_day=draft.meal_count_per_day,
            desserts_enabled=draft.desserts_enabled,
            active_slots=active_slots,
            week_mood=draft.week_mood,
            weekly_notes=draft.weekly_notes,
            pantry_considered=draft.pantry_considered,
            context_payload=draft.context_payload,
        )
        self._session.add(record)
        await self._session.flush()
        return PlanDraftResult(
            weekly_plan_id=record.id,
            start_date=record.start_date,
            end_date=record.end_date,
            active_slots=list(record.active_slots),
            pantry_considered=record.pantry_considered,
        )


def build_planning_repositories(session: AsyncSession) -> PlanningRepositories:
    return PlanningRepositories(
        user_repository=SqlAlchemyPlanningUserRepository(session),
        household_repository=SqlAlchemyPlanningHouseholdRepository(session),
        weekly_plan_repository=SqlAlchemyWeeklyPlanRepository(session),
    )
