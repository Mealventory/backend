"""Persist reviewed batch idempotency results atomically with inventory writes.

Revision ID: 20261022_0008
Revises: 20261004_0007
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20261022_0008"
down_revision = "20261004_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batch_idempotency_records",
        sa.Column("household_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("households.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint(
            "household_id", "user_id", "idempotency_key",
            name="pk_batch_idempotency_records",
        ),
        schema="public",
    )
    op.create_index(
        "idx_batch_idempotency_created",
        "batch_idempotency_records",
        ["created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("idx_batch_idempotency_created",
                  table_name="batch_idempotency_records", schema="public")
    op.drop_table("batch_idempotency_records", schema="public")
