from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.feedback import (
        DishFeedbackEventRecord,
        HouseholdDishPolicyRecord,
    )
    from aimealplanner.infrastructure.db.models.ingredient import IngredientRecord
    from aimealplanner.infrastructure.db.models.plan import PlannedMealItemRecord


class DishRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "dishes"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_dishes_canonical_key"),
        Index("ix_dishes_normalized_name", "normalized_name"),
    )

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_key: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text())
    base_servings: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    recipe: Mapped[DishRecipeRecord | None] = relationship(
        back_populates="dish",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ingredients: Mapped[list[DishIngredientRecord]] = relationship(
        back_populates="dish",
        cascade="all, delete-orphan",
        order_by="DishIngredientRecord.position",
    )
    planned_meal_items: Mapped[list[PlannedMealItemRecord]] = relationship(back_populates="dish")
    feedback_events: Mapped[list[DishFeedbackEventRecord]] = relationship(back_populates="dish")
    household_policies: Mapped[list[HouseholdDishPolicyRecord]] = relationship(
        back_populates="dish",
    )


class DishRecipeRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "dish_recipes"
    __table_args__ = (UniqueConstraint("dish_id", name="uq_dish_recipes_dish_id"),)

    dish_id: Mapped[UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
    )
    preparation_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cooking_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    serving_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    prep_time_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    cook_time_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    serving_notes: Mapped[str | None] = mapped_column(Text())

    dish: Mapped[DishRecord] = relationship(back_populates="recipe")


class DishIngredientRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "dish_ingredients"
    __table_args__ = (Index("ix_dish_ingredients_dish_id_position", "dish_id", "position"),)

    dish_id: Mapped[UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    quantity_unit: Mapped[str | None] = mapped_column(String(32))
    preparation_note: Mapped[str | None] = mapped_column(Text())
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    dish: Mapped[DishRecord] = relationship(back_populates="ingredients")
    ingredient: Mapped[IngredientRecord] = relationship(back_populates="dish_ingredients")
