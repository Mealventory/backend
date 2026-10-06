"""Add household activity events.

Revision ID: 20261004_0007
Revises: 20261003_0006
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa


revision = "20261004_0007"
down_revision = "20261003_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "household_activity_events",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "household_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("actor_name", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "action IN ('added','updated','moved','consumed','discarded','deleted','shopping_added')",
            name="ck_household_activity_action",
        ),
        sa.CheckConstraint(
            "entity_type IN ('inventory','shopping')",
            name="ck_household_activity_entity_type",
        ),
        schema="public",
    )
    op.create_index(
        "idx_household_activity_household_created",
        "household_activity_events",
        ["household_id", "created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_household_activity_household_created",
        table_name="household_activity_events",
        schema="public",
    )
    op.drop_table("household_activity_events", schema="public")
