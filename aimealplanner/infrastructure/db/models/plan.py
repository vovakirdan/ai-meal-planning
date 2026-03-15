from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.enums import (
    MealSlot,
    PlannedMealStatus,
    WeeklyPlanStatus,
    build_str_enum,
)
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.dish import DishRecord
    from aimealplanner.infrastructure.db.models.feedback import DishFeedbackEventRecord
    from aimealplanner.infrastructure.db.models.household import HouseholdRecord
    from aimealplanner.infrastructure.db.models.shopping import ShoppingListRecord

_ACTIVE_SLOTS_TEMPLATE_CHECK = """
active_slots = CASE
    WHEN meal_count_per_day = 2 AND desserts_enabled = false
        THEN ARRAY['breakfast', 'dinner']::VARCHAR[]
    WHEN meal_count_per_day = 2 AND desserts_enabled = true
        THEN ARRAY['breakfast', 'dinner', 'dessert']::VARCHAR[]
    WHEN meal_count_per_day = 3 AND desserts_enabled = false
        THEN ARRAY['breakfast', 'lunch', 'dinner']::VARCHAR[]
    WHEN meal_count_per_day = 3 AND desserts_enabled = true
        THEN ARRAY['breakfast', 'lunch', 'dinner', 'dessert']::VARCHAR[]
    WHEN meal_count_per_day = 4 AND desserts_enabled = false
        THEN ARRAY['breakfast', 'lunch', 'dinner', 'snack_1']::VARCHAR[]
    WHEN meal_count_per_day = 4 AND desserts_enabled = true
        THEN ARRAY['breakfast', 'lunch', 'dinner', 'snack_1', 'dessert']::VARCHAR[]
    WHEN meal_count_per_day = 5 AND desserts_enabled = false
        THEN ARRAY['breakfast', 'lunch', 'dinner', 'snack_1', 'snack_2']::VARCHAR[]
    WHEN meal_count_per_day = 5 AND desserts_enabled = true
        THEN ARRAY['breakfast', 'lunch', 'dinner', 'snack_1', 'snack_2', 'dessert']::VARCHAR[]
END
""".strip()


class WeeklyPlanRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "weekly_plans"
    __table_args__ = (
        Index(
            "ix_weekly_plans_household_id_status_start_date",
            "household_id",
            "status",
            "start_date",
        ),
        CheckConstraint("meal_count_per_day BETWEEN 2 AND 5", name="meal_count_per_day"),
        CheckConstraint("end_date >= start_date", name="weekly_plan_date_range"),
        CheckConstraint(
            _ACTIVE_SLOTS_TEMPLATE_CHECK,
            name="weekly_plan_active_slots_template",
        ),
    )

    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[WeeklyPlanStatus] = mapped_column(
        build_str_enum(WeeklyPlanStatus, name="weekly_plan_status"),
        nullable=False,
        default=WeeklyPlanStatus.DRAFT,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Moscow")
    meal_count_per_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    desserts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_slots: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    week_mood: Mapped[str | None] = mapped_column(String(128))
    weekly_notes: Mapped[str | None] = mapped_column(Text())
    pantry_considered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    context_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    household: Mapped[HouseholdRecord] = relationship(back_populates="weekly_plans")
    planned_meals: Mapped[list[PlannedMealRecord]] = relationship(
        back_populates="weekly_plan",
        cascade="all, delete-orphan",
        order_by="(PlannedMealRecord.meal_date, PlannedMealRecord.slot)",
    )
    shopping_lists: Mapped[list[ShoppingListRecord]] = relationship(
        back_populates="weekly_plan",
        cascade="all, delete-orphan",
    )


class PlannedMealRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "planned_meals"
    __table_args__ = (
        UniqueConstraint(
            "weekly_plan_id", "meal_date", "slot", name="uq_planned_meals_plan_date_slot"
        ),
    )

    weekly_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    meal_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[MealSlot] = mapped_column(
        build_str_enum(MealSlot, name="meal_slot"),
        nullable=False,
    )
    status: Mapped[PlannedMealStatus] = mapped_column(
        build_str_enum(PlannedMealStatus, name="planned_meal_status"),
        nullable=False,
        default=PlannedMealStatus.PLANNED,
    )
    note: Mapped[str | None] = mapped_column(Text())

    weekly_plan: Mapped[WeeklyPlanRecord] = relationship(back_populates="planned_meals")
    items: Mapped[list[PlannedMealItemRecord]] = relationship(
        back_populates="planned_meal",
        cascade="all, delete-orphan",
        order_by="PlannedMealItemRecord.position",
    )


class PlannedMealItemRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "planned_meal_items"
    __table_args__ = (
        UniqueConstraint("planned_meal_id", "position", name="uq_planned_meal_items_meal_position"),
    )

    planned_meal_id: Mapped[UUID] = mapped_column(
        ForeignKey("planned_meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dish_id: Mapped[UUID | None] = mapped_column(ForeignKey("dishes.id", ondelete="SET NULL"))
    snapshot_name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    adaptation_notes: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)

    planned_meal: Mapped[PlannedMealRecord] = relationship(back_populates="items")
    dish: Mapped[DishRecord | None] = relationship(back_populates="planned_meal_items")
    feedback_events: Mapped[list[DishFeedbackEventRecord]] = relationship(
        back_populates="planned_meal_item",
    )
