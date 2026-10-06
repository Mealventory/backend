"""Baseline the current shared-household schema.

Revision ID: 20261002_0001
Revises:
Create Date: 2026-10-02
"""
from pathlib import Path

from alembic import op


revision = "20261002_0001"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = (
    Path(__file__).resolve().parents[1]
    / "sql"
    / "20261002_0001_current_household_baseline.sql"
)


def upgrade() -> None:
    # The immutable SQL snapshot preserves PostgreSQL enums, constraints,
    # compound foreign keys, triggers, and defaults that are not fully modeled
    # by the legacy SQLAlchemy mappings yet.
    op.get_bind().exec_driver_sql(BASELINE_SQL.read_text())


def downgrade() -> None:
    # Downgrading the baseline is destructive and is intended only for
    # disposable development/test databases.
    for table in (
        "household_recipe_completions",
        "household_saved_recipes",
        "device_push_tokens",
        "household_stores",
        "shopping_list_items",
        "recipe_ingredients",
        "recipes",
        "inventory_items",
        "foods",
        "storage_locations",
        "household_members",
        "households",
    ):
        op.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")

    op.execute("DROP FUNCTION IF EXISTS public.update_updated_at_column()")
    op.execute("DROP TYPE IF EXISTS public.item_status")
    op.execute("DROP TYPE IF EXISTS public.storage_zone")
    op.execute("DROP TYPE IF EXISTS public.member_role")
