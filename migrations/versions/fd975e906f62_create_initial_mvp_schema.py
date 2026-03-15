"""create initial mvp schema

Revision ID: fd975e906f62
Revises:
Create Date: 2026-03-15 14:35:11.071517

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "fd975e906f62"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

repeatability_mode_enum = postgresql.ENUM(
    "balanced",
    "more_variety",
    "more_repeatability",
    name="repeatability_mode",
    create_type=False,
)
dish_feedback_verdict_enum = postgresql.ENUM(
    "never_again",
    "rarely_repeat",
    "can_repeat",
    "favorite",
    name="dish_feedback_verdict",
    create_type=False,
)
pantry_stock_level_enum = postgresql.ENUM(
    "has",
    "low",
    "none",
    name="pantry_stock_level",
    create_type=False,
)
weekly_plan_status_enum = postgresql.ENUM(
    "draft",
    "confirmed",
    "archived",
    name="weekly_plan_status",
    create_type=False,
)
meal_slot_enum = postgresql.ENUM(
    "breakfast",
    "lunch",
    "dinner",
    "snack_1",
    "snack_2",
    "dessert",
    name="meal_slot",
    create_type=False,
)
planned_meal_status_enum = postgresql.ENUM(
    "planned",
    "replaced",
    "skipped",
    "prepared",
    name="planned_meal_status",
    create_type=False,
)
shopping_list_availability_status_enum = postgresql.ENUM(
    "need_to_buy",
    "partially_have",
    "already_have",
    name="shopping_list_availability_status",
    create_type=False,
)


def _public_table_exists(bind: sa.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names(schema="public")


def _create_or_upgrade_users_table(bind: sa.Connection) -> None:
    if not _public_table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("daily_feedback_reminder_enabled", sa.Boolean(), nullable=False),
            sa.Column("daily_feedback_reminder_time", sa.Time(), nullable=True),
            sa.Column("weekly_planning_reminder_enabled", sa.Boolean(), nullable=False),
            sa.Column("weekly_planning_reminder_day_of_week", sa.SmallInteger(), nullable=True),
            sa.Column("weekly_planning_reminder_time", sa.Time(), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "weekly_planning_reminder_day_of_week BETWEEN 0 AND 6",
                name=op.f("ck_users_weekly_planning_reminder_day_of_week_range"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
            sa.UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        )
    else:
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)")
        op.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS daily_feedback_reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_feedback_reminder_time TIME")
        op.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS weekly_planning_reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        op.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS weekly_planning_reminder_day_of_week SMALLINT
            """
        )
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_planning_reminder_time TIME")
        op.execute("UPDATE users SET timezone = 'Europe/Moscow' WHERE timezone IS NULL")
        op.execute("ALTER TABLE users ALTER COLUMN timezone SET NOT NULL")
        op.execute("ALTER TABLE users ALTER COLUMN daily_feedback_reminder_enabled DROP DEFAULT")
        op.execute("ALTER TABLE users ALTER COLUMN weekly_planning_reminder_enabled DROP DEFAULT")
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'uq_users_telegram_user_id'
                ) THEN
                    ALTER TABLE users
                    ADD CONSTRAINT uq_users_telegram_user_id UNIQUE (telegram_user_id);
                END IF;
            END
            $$;
            """
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_users_weekly_planning_reminder_day_of_week_range'
                ) THEN
                    ALTER TABLE users
                    ADD CONSTRAINT ck_users_weekly_planning_reminder_day_of_week_range
                    CHECK (weekly_planning_reminder_day_of_week BETWEEN 0 AND 6);
                END IF;
            END
            $$;
            """
        )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_users_daily_feedback_reminder_schedule
        ON users (daily_feedback_reminder_enabled, daily_feedback_reminder_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_users_weekly_planning_reminder_schedule
        ON users (
            weekly_planning_reminder_enabled,
            weekly_planning_reminder_day_of_week,
            weekly_planning_reminder_time
        )
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    bind = op.get_bind()
    repeatability_mode_enum.create(bind, checkfirst=True)
    dish_feedback_verdict_enum.create(bind, checkfirst=True)
    pantry_stock_level_enum.create(bind, checkfirst=True)
    weekly_plan_status_enum.create(bind, checkfirst=True)
    meal_slot_enum.create(bind, checkfirst=True)
    planned_meal_status_enum.create(bind, checkfirst=True)
    shopping_list_availability_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "dishes",
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_key", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("base_servings", sa.SmallInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dishes")),
        sa.UniqueConstraint("canonical_key", name="uq_dishes_canonical_key"),
    )
    op.create_index("ix_dishes_normalized_name", "dishes", ["normalized_name"], unique=False)
    op.create_table(
        "ingredients",
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("shopping_category", sa.String(length=64), nullable=True),
        sa.Column("default_unit", sa.String(length=32), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredients")),
        sa.UniqueConstraint("normalized_name", name="uq_ingredients_normalized_name"),
    )
    _create_or_upgrade_users_table(bind)
    op.create_table(
        "dish_ingredients",
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("quantity_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("quantity_unit", sa.String(length=32), nullable=True),
        sa.Column("preparation_note", sa.Text(), nullable=True),
        sa.Column("is_optional", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_dish_ingredients_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_dish_ingredients_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dish_ingredients")),
    )
    op.create_index(
        "ix_dish_ingredients_dish_id_position",
        "dish_ingredients",
        ["dish_id", "position"],
        unique=False,
    )
    op.create_table(
        "dish_recipes",
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("preparation_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cooking_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("serving_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prep_time_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("cook_time_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("serving_notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_dish_recipes_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dish_recipes")),
        sa.UniqueConstraint("dish_id", name="uq_dish_recipes_dish_id"),
    )
    op.create_table(
        "households",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("default_meal_count_per_day", sa.SmallInteger(), nullable=False),
        sa.Column("desserts_enabled", sa.Boolean(), nullable=False),
        sa.Column("repeatability_mode", repeatability_mode_enum, nullable=False),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "default_meal_count_per_day BETWEEN 2 AND 5",
            name=op.f("ck_households_default_meal_count_per_day"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_households_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_households")),
        sa.UniqueConstraint("user_id", name="uq_households_user_id"),
    )
    op.create_table(
        "household_dish_policies",
        sa.Column("household_id", sa.UUID(), nullable=False),
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("verdict", dish_feedback_verdict_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_household_dish_policies_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_household_dish_policies_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_dish_policies")),
        sa.UniqueConstraint(
            "household_id", "dish_id", name="uq_household_dish_policies_household_id_dish_id"
        ),
    )
    op.create_table(
        "household_members",
        sa.Column("household_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("constraints", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("favorite_cuisines", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("profile_note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_household_members_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_members")),
        sa.UniqueConstraint(
            "household_id", "display_name", name="uq_household_members_household_id_display_name"
        ),
    )
    op.create_table(
        "pantry_items",
        sa.Column("household_id", sa.UUID(), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("quantity_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("quantity_unit", sa.String(length=32), nullable=True),
        sa.Column("stock_level", pantry_stock_level_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_pantry_items_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_pantry_items_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pantry_items")),
        sa.UniqueConstraint(
            "household_id", "ingredient_id", name="uq_pantry_items_household_id_ingredient_id"
        ),
    )
    op.create_table(
        "weekly_plans",
        sa.Column("household_id", sa.UUID(), nullable=False),
        sa.Column("status", weekly_plan_status_enum, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("meal_count_per_day", sa.SmallInteger(), nullable=False),
        sa.Column("desserts_enabled", sa.Boolean(), nullable=False),
        sa.Column("active_slots", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("week_mood", sa.String(length=128), nullable=True),
        sa.Column("weekly_notes", sa.Text(), nullable=True),
        sa.Column("pantry_considered", sa.Boolean(), nullable=False),
        sa.Column("context_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date >= start_date", name=op.f("ck_weekly_plans_weekly_plan_date_range")
        ),
        sa.CheckConstraint(
            "meal_count_per_day BETWEEN 2 AND 5", name=op.f("ck_weekly_plans_meal_count_per_day")
        ),
        sa.CheckConstraint(
            """
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
                    THEN ARRAY[
                        'breakfast',
                        'lunch',
                        'dinner',
                        'snack_1',
                        'snack_2',
                        'dessert'
                    ]::VARCHAR[]
            END
            """.strip(),
            name=op.f("ck_weekly_plans_weekly_plan_active_slots_template"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_weekly_plans_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weekly_plans")),
    )
    op.create_index(
        "ix_weekly_plans_household_id_status_start_date",
        "weekly_plans",
        ["household_id", "status", "start_date"],
        unique=False,
    )
    op.create_table(
        "planned_meals",
        sa.Column("weekly_plan_id", sa.UUID(), nullable=False),
        sa.Column("meal_date", sa.Date(), nullable=False),
        sa.Column("slot", meal_slot_enum, nullable=False),
        sa.Column("status", planned_meal_status_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["weekly_plan_id"],
            ["weekly_plans.id"],
            name=op.f("fk_planned_meals_weekly_plan_id_weekly_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_meals")),
        sa.UniqueConstraint(
            "weekly_plan_id", "meal_date", "slot", name="uq_planned_meals_plan_date_slot"
        ),
    )
    op.create_table(
        "shopping_lists",
        sa.Column("weekly_plan_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["weekly_plan_id"],
            ["weekly_plans.id"],
            name=op.f("fk_shopping_lists_weekly_plan_id_weekly_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_lists")),
        sa.UniqueConstraint(
            "weekly_plan_id", "version", name="uq_shopping_lists_weekly_plan_id_version"
        ),
    )
    op.create_table(
        "planned_meal_items",
        sa.Column("planned_meal_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("dish_id", sa.UUID(), nullable=True),
        sa.Column("snapshot_name", sa.String(length=255), nullable=False),
        sa.Column("snapshot_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("adaptation_notes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_planned_meal_items_dish_id_dishes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["planned_meal_id"],
            ["planned_meals.id"],
            name=op.f("fk_planned_meal_items_planned_meal_id_planned_meals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_meal_items")),
        sa.UniqueConstraint(
            "planned_meal_id", "position", name="uq_planned_meal_items_meal_position"
        ),
    )
    op.create_table(
        "shopping_list_items",
        sa.Column("shopping_list_id", sa.UUID(), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("quantity_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("quantity_unit", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("availability_status", shopping_list_availability_status_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_shopping_list_items_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shopping_list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_shopping_list_items_shopping_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_list_items")),
    )
    op.create_index(
        "ix_shopping_list_items_list_id_position",
        "shopping_list_items",
        ["shopping_list_id", "position"],
        unique=False,
    )
    op.create_table(
        "dish_feedback_events",
        sa.Column("household_member_id", sa.UUID(), nullable=False),
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("planned_meal_item_id", sa.UUID(), nullable=True),
        sa.Column("feedback_date", sa.Date(), nullable=False),
        sa.Column("verdict", dish_feedback_verdict_enum, nullable=False),
        sa.Column("raw_comment", sa.Text(), nullable=True),
        sa.Column("normalized_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_dish_feedback_events_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_member_id"],
            ["household_members.id"],
            name=op.f("fk_dish_feedback_events_household_member_id_household_members"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["planned_meal_item_id"],
            ["planned_meal_items.id"],
            name=op.f("fk_dish_feedback_events_planned_meal_item_id_planned_meal_items"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dish_feedback_events")),
    )
    op.create_index(
        "ix_dish_feedback_events_dish_id_feedback_date",
        "dish_feedback_events",
        ["dish_id", "feedback_date"],
        unique=False,
    )
    op.create_index(
        "ix_dish_feedback_events_member_id_feedback_date",
        "dish_feedback_events",
        ["household_member_id", "feedback_date"],
        unique=False,
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_planned_meal_for_weekly_plan()
        RETURNS trigger AS $$
        DECLARE
            plan_start_date date;
            plan_end_date date;
            plan_active_slots varchar[];
        BEGIN
            SELECT start_date, end_date, active_slots
            INTO plan_start_date, plan_end_date, plan_active_slots
            FROM weekly_plans
            WHERE id = NEW.weekly_plan_id;

            IF plan_start_date IS NULL THEN
                RAISE EXCEPTION
                    'weekly_plans row % not found for planned_meals row',
                    NEW.weekly_plan_id;
            END IF;

            IF NEW.meal_date < plan_start_date OR NEW.meal_date > plan_end_date THEN
                RAISE EXCEPTION
                    'meal_date % must be within weekly plan range [% - %]',
                    NEW.meal_date,
                    plan_start_date,
                    plan_end_date;
            END IF;

            IF NOT (NEW.slot::text = ANY(plan_active_slots)) THEN
                RAISE EXCEPTION
                    'slot % is not active for weekly plan %',
                    NEW.slot,
                    NEW.weekly_plan_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_planned_meals_validate_plan_context
        BEFORE INSERT OR UPDATE OF weekly_plan_id, meal_date, slot
        ON planned_meals
        FOR EACH ROW
        EXECUTE FUNCTION validate_planned_meal_for_weekly_plan();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_weekly_plan_confirmation()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.status::text = 'confirmed' THEN
                IF EXISTS (
                    SELECT 1
                    FROM planned_meal_items AS pmi
                    JOIN planned_meals AS pm ON pm.id = pmi.planned_meal_id
                    WHERE pm.weekly_plan_id = NEW.id
                      AND pmi.dish_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'confirmed weekly plan % requires dish_id for every planned meal item',
                        NEW.id;
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_plans_require_dish_ids_before_confirm
        BEFORE INSERT OR UPDATE OF status
        ON weekly_plans
        FOR EACH ROW
        EXECUTE FUNCTION validate_weekly_plan_confirmation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_planned_meal_item_for_confirmed_plan()
        RETURNS trigger AS $$
        DECLARE
            plan_status text;
        BEGIN
            SELECT wp.status::text
            INTO plan_status
            FROM weekly_plans AS wp
            JOIN planned_meals AS pm ON pm.weekly_plan_id = wp.id
            WHERE pm.id = NEW.planned_meal_id;

            IF plan_status IS NULL THEN
                RAISE EXCEPTION
                    'planned_meals row % not found for planned_meal_items row',
                    NEW.planned_meal_id;
            END IF;

            IF plan_status = 'confirmed' AND NEW.dish_id IS NULL THEN
                RAISE EXCEPTION 'confirmed planned meal items require dish_id';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_planned_meal_items_require_dish_id_for_confirmed_plan
        BEFORE INSERT OR UPDATE OF planned_meal_id, dish_id
        ON planned_meal_items
        FOR EACH ROW
        EXECUTE FUNCTION validate_planned_meal_item_for_confirmed_plan();
        """
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    bind = op.get_bind()

    op.execute(
        """
        DROP TRIGGER IF EXISTS
        trg_planned_meal_items_require_dish_id_for_confirmed_plan
        ON planned_meal_items
        """
    )
    op.execute("DROP FUNCTION IF EXISTS validate_planned_meal_item_for_confirmed_plan()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_weekly_plans_require_dish_ids_before_confirm ON weekly_plans"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_weekly_plan_confirmation()")
    op.execute("DROP TRIGGER IF EXISTS trg_planned_meals_validate_plan_context ON planned_meals")
    op.execute("DROP FUNCTION IF EXISTS validate_planned_meal_for_weekly_plan()")

    op.drop_index(
        "ix_dish_feedback_events_member_id_feedback_date", table_name="dish_feedback_events"
    )
    op.drop_index(
        "ix_dish_feedback_events_dish_id_feedback_date", table_name="dish_feedback_events"
    )
    op.drop_table("dish_feedback_events")
    op.drop_index("ix_shopping_list_items_list_id_position", table_name="shopping_list_items")
    op.drop_table("shopping_list_items")
    op.drop_table("planned_meal_items")
    op.drop_table("shopping_lists")
    op.drop_table("planned_meals")
    op.drop_index("ix_weekly_plans_household_id_status_start_date", table_name="weekly_plans")
    op.drop_table("weekly_plans")
    op.drop_table("pantry_items")
    op.drop_table("household_members")
    op.drop_table("household_dish_policies")
    op.drop_table("households")
    op.drop_table("dish_recipes")
    op.drop_index("ix_dish_ingredients_dish_id_position", table_name="dish_ingredients")
    op.drop_table("dish_ingredients")
    op.drop_index("ix_users_weekly_planning_reminder_schedule", table_name="users")
    op.drop_index("ix_users_daily_feedback_reminder_schedule", table_name="users")
    op.drop_table("users")
    op.drop_table("ingredients")
    op.drop_index("ix_dishes_normalized_name", table_name="dishes")
    op.drop_table("dishes")

    shopping_list_availability_status_enum.drop(bind, checkfirst=True)
    planned_meal_status_enum.drop(bind, checkfirst=True)
    meal_slot_enum.drop(bind, checkfirst=True)
    weekly_plan_status_enum.drop(bind, checkfirst=True)
    pantry_stock_level_enum.drop(bind, checkfirst=True)
    dish_feedback_verdict_enum.drop(bind, checkfirst=True)
    repeatability_mode_enum.drop(bind, checkfirst=True)
    # ### end Alembic commands ###
