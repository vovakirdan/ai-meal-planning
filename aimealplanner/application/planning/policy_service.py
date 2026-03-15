# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aimealplanner.application.planning.browsing_dto import StoredPlanItemView
from aimealplanner.application.planning.generation_dto import WeeklyPlanGenerationContext
from aimealplanner.application.planning.repositories import (
    PlanningRepositories,
    PlanningRepositoryBundleFactory,
)
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict


@dataclass(frozen=True, slots=True)
class DishPolicyUpdateResult:
    updated_item: StoredPlanItemView


@dataclass(frozen=True, slots=True)
class DishPolicyRemovalResult:
    updated_meal_id: UUID


class PolicyReasonClient(Protocol):
    async def normalize_policy_reason(
        self,
        *,
        item_view: StoredPlanItemView,
        generation_context: WeeklyPlanGenerationContext,
        verdict_label: str,
        raw_reason: str,
    ) -> str | None: ...


class DishPolicyService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repositories_factory: PlanningRepositoryBundleFactory,
        reason_client: PolicyReasonClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._reason_client = reason_client

    async def set_household_policy(
        self,
        telegram_user_id: int,
        planned_meal_item_id: UUID,
        *,
        verdict: DishFeedbackVerdict,
        note: str | None = None,
        raw_reason: str | None = None,
    ) -> DishPolicyUpdateResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            existing_item = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                planned_meal_item_id,
            )
            if existing_item is None:
                raise ValueError("Не удалось открыть выбранное блюдо.")

            normalized_note = note
            if raw_reason and self._reason_client is not None:
                generation_context = (
                    await repositories.weekly_plan_repository.get_generation_context(
                        existing_item.weekly_plan_id,
                    )
                )
                if generation_context is not None:
                    normalized_note = await self._reason_client.normalize_policy_reason(
                        item_view=existing_item,
                        generation_context=generation_context,
                        verdict_label=verdict.value,
                        raw_reason=raw_reason,
                    )

            dish_id = await repositories.weekly_plan_repository.ensure_item_dish(
                household_id,
                planned_meal_item_id,
            )
            await repositories.weekly_plan_repository.upsert_household_dish_policy(
                household_id,
                dish_id,
                verdict,
                normalized_note,
            )
            await session.commit()

            updated_item = await repositories.weekly_plan_repository.get_item_view(
                household_id,
                planned_meal_item_id,
            )
            if updated_item is None:
                raise ValueError("Не удалось прочитать обновленное блюдо.")
            return DishPolicyUpdateResult(updated_item=updated_item)

    async def remove_item_from_current_plan(
        self,
        telegram_user_id: int,
        planned_meal_item_id: UUID,
    ) -> DishPolicyRemovalResult:
        async with self._session_factory() as session:
            repositories = self._repositories_factory(session)
            household_id = await _resolve_household_id(repositories, telegram_user_id)
            meal_id = await repositories.weekly_plan_repository.delete_item(
                household_id,
                planned_meal_item_id,
            )
            await session.commit()
            return DishPolicyRemovalResult(updated_meal_id=meal_id)


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
