from typing import cast

import sqlalchemy as sa
from aimealplanner.infrastructure.db import models as db_models  # noqa: F401
from aimealplanner.infrastructure.db.base import Base
from aimealplanner.infrastructure.db.enums import DishFeedbackVerdict, RepeatabilityMode


def test_metadata_contains_core_mvp_tables() -> None:
    table_names = set(Base.metadata.tables)

    assert {
        "users",
        "households",
        "household_members",
        "ingredients",
        "pantry_items",
        "dishes",
        "dish_recipes",
        "dish_ingredients",
        "weekly_plans",
        "planned_meals",
        "planned_meal_items",
        "household_dish_policies",
        "dish_feedback_events",
        "shopping_lists",
        "shopping_list_items",
    }.issubset(table_names)


def test_metadata_uses_enum_values_and_timezone_aware_audit_columns() -> None:
    repeatability_type = cast(
        sa.Enum,
        Base.metadata.tables["households"].c.repeatability_mode.type,
    )
    feedback_type = cast(
        sa.Enum,
        Base.metadata.tables["dish_feedback_events"].c.verdict.type,
    )
    onboarding_completed_at_type = cast(
        sa.DateTime,
        Base.metadata.tables["households"].c.onboarding_completed_at.type,
    )
    confirmed_at_type = cast(
        sa.DateTime,
        Base.metadata.tables["weekly_plans"].c.confirmed_at.type,
    )
    weekly_plan_constraints = {
        constraint.name for constraint in Base.metadata.tables["weekly_plans"].constraints
    }

    assert repeatability_type.enums == [item.value for item in RepeatabilityMode]
    assert feedback_type.enums == [item.value for item in DishFeedbackVerdict]
    assert onboarding_completed_at_type.timezone is True
    assert confirmed_at_type.timezone is True
    assert "ck_weekly_plans_weekly_plan_active_slots_template" in weekly_plan_constraints
