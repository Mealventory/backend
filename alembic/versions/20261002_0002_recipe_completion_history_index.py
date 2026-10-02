"""Index household recipe completion history.

Revision ID: 20261002_0002
Revises: 20261002_0001
Create Date: 2026-10-02
"""
from alembic import op


revision = "20261002_0002"
down_revision = "20261002_0001"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_recipe_completions_household_created"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "household_recipe_completions",
        ["household_id", "created_at"],
        unique=False,
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        INDEX_NAME,
        table_name="household_recipe_completions",
        schema="public",
    )
