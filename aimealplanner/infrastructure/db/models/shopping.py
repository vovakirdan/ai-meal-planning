from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.enums import (
    ShoppingListAvailabilityStatus,
    build_str_enum,
)
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.ingredient import IngredientRecord
    from aimealplanner.infrastructure.db.models.plan import WeeklyPlanRecord


class ShoppingListRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "shopping_lists"
    __table_args__ = (
        UniqueConstraint(
            "weekly_plan_id", "version", name="uq_shopping_lists_weekly_plan_id_version"
        ),
    )

    weekly_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    weekly_plan: Mapped[WeeklyPlanRecord] = relationship(back_populates="shopping_lists")
    items: Mapped[list[ShoppingListItemRecord]] = relationship(
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        order_by="ShoppingListItemRecord.position",
    )


class ShoppingListItemRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "shopping_list_items"
    __table_args__ = (
        Index("ix_shopping_list_items_list_id_position", "shopping_list_id", "position"),
    )

    shopping_list_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    quantity_unit: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(64))
    availability_status: Mapped[ShoppingListAvailabilityStatus] = mapped_column(
        build_str_enum(
            ShoppingListAvailabilityStatus,
            name="shopping_list_availability_status",
        ),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text())

    shopping_list: Mapped[ShoppingListRecord] = relationship(back_populates="items")
    ingredient: Mapped[IngredientRecord] = relationship(back_populates="shopping_list_items")
