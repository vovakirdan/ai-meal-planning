from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.mixins import TimestampedUUIDMixin

if TYPE_CHECKING:
    from aimealplanner.infrastructure.db.models.dish import DishIngredientRecord
    from aimealplanner.infrastructure.db.models.household import PantryItemRecord
    from aimealplanner.infrastructure.db.models.shopping import ShoppingListItemRecord


class IngredientRecord(TimestampedUUIDMixin, Base):
    __tablename__ = "ingredients"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_ingredients_normalized_name"),)

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    shopping_category: Mapped[str | None] = mapped_column(String(64))
    default_unit: Mapped[str | None] = mapped_column(String(32))

    pantry_items: Mapped[list[PantryItemRecord]] = relationship(back_populates="ingredient")
    dish_ingredients: Mapped[list[DishIngredientRecord]] = relationship(back_populates="ingredient")
    shopping_list_items: Mapped[list[ShoppingListItemRecord]] = relationship(
        back_populates="ingredient",
    )
