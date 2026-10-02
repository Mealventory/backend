"""Make low-stock tracking automatic at a fixed ten percent.

Revision ID: 20261002_0004
Revises: 20261002_0003
Create Date: 2026-10-02
"""
from alembic import op


revision = "20261002_0004"
down_revision = "20261002_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing pantry rows predate automatic tracking. Treat their current
    # quantity at migration time as their starting amount so they begin at 100%.
    op.execute(
        """
        UPDATE public.inventory_items
        SET quantity_tracking_enabled = true,
            initial_quantity = COALESCE(initial_quantity, quantity),
            low_stock_threshold_percent = 10
        WHERE quantity > 0
        """
    )


def downgrade() -> None:
    # Data migration only: keep captured starting quantities rather than
    # discarding user inventory metadata on rollback.
    pass
