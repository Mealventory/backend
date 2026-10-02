"""Track whether a low-stock push was already sent.

Revision ID: 20261002_0005
Revises: 20261002_0004
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "20261002_0005"
down_revision = "20261002_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("low_stock_notified_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("inventory_items", "low_stock_notified_at", schema="public")
