
"""Add waste reasons to household activity events.

Revision ID: 20261016_0008
Revises: 20261004_0007
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20261016_0008"
down_revision = "20261004_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "household_activity_events",
        sa.Column("reason", sa.String(length=40), nullable=True),
        schema="public",
    )

    op.create_check_constraint(
        "ck_household_activity_waste_reason",
        "household_activity_events",
        "reason IS NULL OR reason IN "
        "('expired', 'spoiled', 'bought_too_much', 'didnt_like', 'other')",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_household_activity_waste_reason",
        "household_activity_events",
        schema="public",
        type_="check",
    )

    op.drop_column(
        "household_activity_events",
        "reason",
        schema="public",
    )
