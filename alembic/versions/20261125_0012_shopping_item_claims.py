"""Add claim columns to shopping_list_items for multi-shopper coordination.

Revision ID: 20261125_0012
Revises: 20261119_0011
"""
from alembic import op
import sqlalchemy as sa

revision = "20261125_0012"
down_revision = "20261119_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shopping_list_items",
        sa.Column("claimed_by", sa.Uuid(as_uuid=False), nullable=True),
        schema="public",
    )
    op.add_column(
        "shopping_list_items",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "shopping_list_items",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.create_index(
        "idx_shopping_claim",
        "shopping_list_items",
        ["household_id", "claimed_by"],
        schema="public",
    )


def downgrade():
    op.drop_index(
        "idx_shopping_claim",
        table_name="shopping_list_items",
        schema="public",
    )
    op.drop_column("shopping_list_items", "claim_expires_at", schema="public")
    op.drop_column("shopping_list_items", "claimed_at", schema="public")
    op.drop_column("shopping_list_items", "claimed_by", schema="public")
