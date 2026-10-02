"""Add quantity tracking metadata for low-stock alerts.

Revision ID: 20261002_0003
Revises: 20261002_0002
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "20261002_0003"
down_revision = "20261002_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column(
            "quantity_tracking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="public",
    )
    op.add_column(
        "inventory_items",
        sa.Column("initial_quantity", sa.Numeric(12, 3), nullable=True),
        schema="public",
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "low_stock_threshold_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("10"),
        ),
        schema="public",
    )
    op.create_check_constraint(
        "ck_inventory_initial_quantity_positive",
        "inventory_items",
        "initial_quantity IS NULL OR (initial_quantity > 0 AND initial_quantity <> 'NaN'::numeric)",
        schema="public",
    )
    op.create_check_constraint(
        "ck_inventory_low_stock_threshold",
        "inventory_items",
        "low_stock_threshold_percent > 0 AND low_stock_threshold_percent <= 100",
        schema="public",
    )
    op.create_check_constraint(
        "ck_inventory_tracking_has_reference",
        "inventory_items",
        "NOT quantity_tracking_enabled OR initial_quantity IS NOT NULL",
        schema="public",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_inventory_tracking_has_reference",
        "inventory_items",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_inventory_low_stock_threshold",
        "inventory_items",
        schema="public",
        type_="check",
    )
    op.drop_constraint(
        "ck_inventory_initial_quantity_positive",
        "inventory_items",
        schema="public",
        type_="check",
    )
    op.drop_column("inventory_items", "low_stock_threshold_percent", schema="public")
    op.drop_column("inventory_items", "initial_quantity", schema="public")
    op.drop_column("inventory_items", "quantity_tracking_enabled", schema="public")
