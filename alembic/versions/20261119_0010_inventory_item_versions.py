"""Version household inventory items to reject stale client edits.

Revision ID: 20261119_0010
Revises: 20261119_0009

Existing rows start at version 1; subsequent writes increment atomically.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261119_0010"
down_revision = "20261119_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory_items",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        schema="public",
    )
    op.create_check_constraint(
        "ck_inventory_item_version_positive",
        "inventory_items",
        "version > 0",
        schema="public",
    )


def downgrade():
    op.drop_constraint(
        "ck_inventory_item_version_positive",
        "inventory_items",
        type_="check",
        schema="public",
    )
    op.drop_column("inventory_items", "version", schema="public")
