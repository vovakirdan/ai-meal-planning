from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict, build_str_enum
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.dish import DishRecord
    from aimealplanner.infrastructure.db.models.household import (
        HouseholdMemberRecord,
        HouseholdRecord,
    )
    from aimealplanner.infrastructure.db.models.plan import PlannedMealItemRecord


class HouseholdDishPolicyRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "household_dish_policies"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "dish_id", name="uq_household_dish_policies_household_id_dish_id"
        ),
    )

    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_id: Mapped[UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
    )
    verdict: Mapped[DishFeedbackVerdict] = mapped_column(
        build_str_enum(DishFeedbackVerdict, name="dish_feedback_verdict"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text())

    household: Mapped[HouseholdRecord] = relationship(back_populates="dish_policies")
    dish: Mapped[DishRecord] = relationship(back_populates="household_policies")


class DishFeedbackEventRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "dish_feedback_events"
    __table_args__ = (
        Index(
            "ix_dish_feedback_events_member_id_feedback_date",
            "household_member_id",
            "feedback_date",
        ),
        Index(
            "ix_dish_feedback_events_dish_id_feedback_date",
            "dish_id",
            "feedback_date",
        ),
    )

    household_member_id: Mapped[UUID] = mapped_column(
        ForeignKey("household_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_id: Mapped[UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
    )
    planned_meal_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("planned_meal_items.id", ondelete="SET NULL"),
    )
    feedback_date: Mapped[date] = mapped_column(Date, nullable=False)
    verdict: Mapped[DishFeedbackVerdict] = mapped_column(
        build_str_enum(DishFeedbackVerdict, name="dish_feedback_verdict"),
        nullable=False,
    )
    raw_comment: Mapped[str | None] = mapped_column(Text())
    normalized_notes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    household_member: Mapped[HouseholdMemberRecord] = relationship(back_populates="feedback_events")
    dish: Mapped[DishRecord] = relationship(back_populates="feedback_events")
    planned_meal_item: Mapped[PlannedMealItemRecord | None] = relationship(
        back_populates="feedback_events",
    )
