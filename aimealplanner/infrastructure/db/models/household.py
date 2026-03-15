from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.enums import (
    PantryStockLevel,
    RepeatabilityMode,
    build_str_enum,
)
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.feedback import (
        DishFeedbackEventRecord,
        HouseholdDishPolicyRecord,
    )
    from aimealplanner.infrastructure.db.models.ingredient import IngredientRecord
    from aimealplanner.infrastructure.db.models.plan import WeeklyPlanRecord
    from aimealplanner.infrastructure.db.models.user import UserRecord


class HouseholdRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "households"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_households_user_id"),
        CheckConstraint(
            "default_meal_count_per_day BETWEEN 2 AND 5", name="default_meal_count_per_day"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    default_meal_count_per_day: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=3,
    )
    desserts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repeatability_mode: Mapped[RepeatabilityMode] = mapped_column(
        build_str_enum(RepeatabilityMode, name="repeatability_mode"),
        nullable=False,
        default=RepeatabilityMode.BALANCED,
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[UserRecord] = relationship(back_populates="household")
    members: Mapped[list[HouseholdMemberRecord]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
        order_by="HouseholdMemberRecord.sort_order",
    )
    pantry_items: Mapped[list[PantryItemRecord]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )
    weekly_plans: Mapped[list[WeeklyPlanRecord]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )
    dish_policies: Mapped[list[HouseholdDishPolicyRecord]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )


class HouseholdMemberRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "household_members"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "display_name", name="uq_household_members_household_id_display_name"
        ),
    )

    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    constraints: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, default=list)
    favorite_cuisines: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list
    )
    profile_note: Mapped[str | None] = mapped_column(Text())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    household: Mapped[HouseholdRecord] = relationship(back_populates="members")
    feedback_events: Mapped[list[DishFeedbackEventRecord]] = relationship(
        back_populates="household_member",
        cascade="all, delete-orphan",
    )


class PantryItemRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "pantry_items"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "ingredient_id", name="uq_pantry_items_household_id_ingredient_id"
        ),
    )

    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    quantity_unit: Mapped[str | None] = mapped_column(String(32))
    stock_level: Mapped[PantryStockLevel] = mapped_column(
        build_str_enum(PantryStockLevel, name="pantry_stock_level"),
        nullable=False,
        default=PantryStockLevel.HAS,
    )
    note: Mapped[str | None] = mapped_column(Text())

    household: Mapped[HouseholdRecord] = relationship(back_populates="pantry_items")
    ingredient: Mapped[IngredientRecord] = relationship(back_populates="pantry_items")
