# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.browsing_dto import (
    StoredPlanDayView,
    StoredPlanItemView,
    StoredPlanMealView,
    StoredPlanOverview,
)
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)


@dataclass(frozen=True, slots=True)
class RenderablePlanOverview:
    weekly_plan_id: UUID
    start_date: date
    end_date: date
    text: str


class PlanningBrowsingService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory

    async def get_latest_draft_overview(self, telegram_user_id: int) -> RenderablePlanOverview:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            user = await repositories.user_repository.get_by_telegram_user_id(telegram_user_id)
            if user is None:
                raise ValueError("Профиль не найден. Сначала отправь /start.")

            household = await repositories.household_repository.get_by_user_id(user.id)
            if household is None or household.onboarding_completed_at is None:
                raise ValueError("Сначала заверши стартовую настройку через /start.")

            latest_draft = await repositories.weekly_plan_repository.get_latest_draft_for_household(
                household.id,
            )
            if latest_draft is None:
                raise ValueError("Текущего черновика пока нет. Создай его командой /plan.")

            overview = await repositories.weekly_plan_repository.get_plan_overview(
                household.id,
                latest_draft.id,
            )
            if overview is None:
                raise ValueError("Не удалось открыть текущий черновик.")

            return RenderablePlanOverview(
                weekly_plan_id=overview.weekly_plan_id,
                start_date=overview.start_date,
                end_date=overview.end_date,
                text=render_plan_overview(overview),
            )

    async def get_day_view(
        self,
        telegram_user_id: int,
        weekly_plan_id: UUID,
        meal_date: date,
    ) -> StoredPlanDayView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            day_view = await repositories.weekly_plan_repository.get_day_view(
                household_id,
                weekly_plan_id,
                meal_date,
            )
            if day_view is None:
                raise ValueError("Не удалось открыть выбранный день плана.")
            return day_view

    async def get_meal_view(
        self,
        telegram_user_id: int,
        planned_meal_id: UUID,
    ) -> StoredPlanMealView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            meal_view = await repositories.weekly_plan_repository.get_meal_view(
                household_id,
                planned_meal_id,
            )
            if meal_view is None:
                raise ValueError("Не удалось открыть выбранный прием пищи.")
            return meal_view

    async def get_item_view(
        self,
        telegram_user_id: int,
        planned_meal_item_id: UUID,
    ) -> StoredPlanItemView:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            item_view = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                planned_meal_item_id,
            )
            if item_view is None:
                raise ValueError("Не удалось открыть выбранное блюдо.")
            return item_view


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


def render_plan_overview(overview: StoredPlanOverview) -> str:
    lines = [
        "Текущий план недели.",
        (
            f"Период: {overview.start_date.strftime('%d.%m.%Y')} - "
            f"{overview.end_date.strftime('%d.%m.%Y')}."
        ),
    ]
    if not overview.days:
        lines.extend(
            [
                "",
                "Черновик уже создан, но блюда для него пока не сгенерированы.",
            ],
        )
        return "\n".join(lines)

    lines.append("")
    lines.append("Выбери день, чтобы посмотреть блюда подробнее.")
    return "\n".join(lines)
