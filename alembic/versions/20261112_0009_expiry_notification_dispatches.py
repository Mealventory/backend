"""Track daily expiry push notification dispatches for idempotency and receipt auditing.

Revision ID: 20261112_0009
Revises: 69b9c45b9a94
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa


revision = "20261112_0009"
down_revision = "69b9c45b9a94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expiry_notification_dispatches",
        sa.Column(
            "household_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dispatched_on", sa.Date(), nullable=False),
        sa.Column(
            "dispatched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "item_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "notifications_accepted",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("ticket_tokens_json", sa.Text(), nullable=True),
        sa.Column("receipts_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "household_id",
            "dispatched_on",
            name="pk_expiry_notification_dispatches",
        ),
        schema="public",
    )
    op.create_index(
        "idx_expiry_notification_dispatches_date",
        "expiry_notification_dispatches",
        ["dispatched_on"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_expiry_notification_dispatches_date",
        table_name="expiry_notification_dispatches",
        schema="public",
    )
    op.drop_table("expiry_notification_dispatches", schema="public")

