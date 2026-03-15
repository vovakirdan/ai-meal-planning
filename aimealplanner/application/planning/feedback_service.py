# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.feedback_dto import (
    ReviewDayOption,
    ReviewDaySession,
    ReviewQueueEntry,
    ReviewStartContext,
)
from aimealplanner.application.planning.generation_dto import WeeklyPlanGenerationContext
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict


@dataclass(frozen=True, slots=True)
class FeedbackSaveResult:
    normalized_notes: dict[str, object]


class FeedbackCommentClient(Protocol):
    async def normalize_feedback_comment(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        household_member_name: str,
        verdict: DishFeedbackVerdict,
        raw_comment: str,
    ) -> dict[str, object]: ...


class DishReviewService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        comment_client: FeedbackCommentClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._comment_client = comment_client

    async def start_review(self, telegram_user_id: int) -> ReviewStartContext:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            latest_plan = (
                await repositories.weekly_plan_repository.get_latest_confirmed_for_household(
                    household_id,
                )
            )
            if latest_plan is None:
                raise ValueError(
                    "Подтвержденного плана пока нет. Сначала подтверди неделю через /week.",
                )

            overview = await repositories.weekly_plan_repository.get_plan_overview(
                household_id,
                latest_plan.id,
            )
            if overview is None:
                raise ValueError("Не удалось открыть подтвержденную неделю.")

            days = [
                ReviewDayOption(
                    meal_date=day.meal_date,
                    meals_count=day.meals_count,
                    items_count=sum(len(meal.item_names) for meal in day.meals),
                )
                for day in overview.days
                if any(meal.item_names for meal in day.meals)
            ]
            if not days:
                raise ValueError("В подтвержденной неделе пока нет блюд для оценки.")

            return ReviewStartContext(
                weekly_plan_id=overview.weekly_plan_id,
                start_date=overview.start_date,
                end_date=overview.end_date,
                days=days,
            )

    async def start_day_review(
        self,
        telegram_user_id: int,
        *,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> ReviewDaySession:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            latest_plan = (
                await repositories.weekly_plan_repository.get_latest_confirmed_for_household(
                    household_id,
                )
            )
            if latest_plan is None or latest_plan.id != weekly_plan_id:
                raise ValueError(
                    "Открой /review заново, чтобы оценить актуальную подтвержденную неделю.",
                )

            day_view = await repositories.weekly_plan_repository.get_day_view(
                household_id,
                weekly_plan_id,
                meal_date,
            )
            if day_view is None:
                raise ValueError("Не удалось открыть выбранный день.")

            members = [
                member
                for member in await repositories.household_repository.list_members(household_id)
                if member.is_active
            ]
            if not members:
                raise ValueError("В семье пока нет активных участников для оценки блюд.")

            entries: list[ReviewQueueEntry] = []
            for meal in day_view.meals:
                meal_view = await repositories.weekly_plan_repository.get_meal_view(
                    household_id,
                    meal.planned_meal_id,
                )
                if meal_view is None:
                    continue
                for item in meal_view.items:
                    for member in members:
                        entries.append(
                            ReviewQueueEntry(
                                planned_meal_item_id=item.planned_meal_item_id,
                                meal_date=meal_view.meal_date,
                                slot=meal_view.slot,
                                dish_name=item.name,
                                household_member_id=member.id,
                                household_member_name=member.display_name,
                            ),
                        )

            if not entries:
                raise ValueError("На этот день пока нет блюд для оценки.")

            return ReviewDaySession(
                weekly_plan_id=weekly_plan_id,
                meal_date=meal_date,
                entries=entries,
            )

    async def save_feedback(
        self,
        telegram_user_id: int,
        *,
        entry: ReviewQueueEntry,
        verdict: DishFeedbackVerdict,
        raw_comment: str | None,
    ) -> FeedbackSaveResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            item_view = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                entry.planned_meal_item_id,
            )
            if item_view is None:
                raise ValueError("Не удалось открыть блюдо для сохранения отзыва.")

            dish_id = item_view.dish_id
            if dish_id is None:
                dish_id = await repositories.weekly_plan_repository.ensure_item_dish(
                    household_id,
                    entry.planned_meal_item_id,
                )

            normalized_notes: dict[str, object] = {}
            if raw_comment and self._comment_client is not None:
                generation_context = (
                    await repositories.weekly_plan_repository.get_generation_context(
                        item_view.weekly_plan_id,
                    )
                )
                if generation_context is not None:
                    normalized_notes = await self._comment_client.normalize_feedback_comment(
                        item_view=item_view,
                        generation_context=generation_context,
                        household_member_name=entry.household_member_name,
                        verdict=verdict,
                        raw_comment=raw_comment,
                    )

            await repositories.weekly_plan_repository.upsert_feedback_event(
                household_id=household_id,
                household_member_id=entry.household_member_id,
                planned_meal_item_id=entry.planned_meal_item_id,
                dish_id=dish_id,
                feedback_date=entry.meal_date,
                verdict=verdict,
                raw_comment=raw_comment,
                normalized_notes=normalized_notes,
            )
            await session.commit()
            return FeedbackSaveResult(normalized_notes=normalized_notes)


async def _resolve_household_id(
    repositories: PlanningRepositories,
    telegram_user_id: int,
) -> UUID:
    user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
    if user is None:
        raise ValueError("Профиль не найден. Сначала отправь /start.")

    household = await repositories.household_repository.get_by_user_id(user.id)
    if household is None or household.onboarding_completed_at is None:
        raise ValueError("Сначала заверши стартовую настройку через /start.")
    return household.id
