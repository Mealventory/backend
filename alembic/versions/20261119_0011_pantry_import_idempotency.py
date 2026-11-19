"""Persist idempotent pantry CSV confirmations.

Revision ID: 20261119_0011
Revises: 20261119_0010
"""
from alembic import op
import sqlalchemy as sa

revision = "20261119_0011"
down_revision = "20261119_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pantry_import_idempotency_records",
        sa.Column("household_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("household_id", "user_id", "idempotency_key",
                                name="pk_pantry_import_idempotency_records"),
        schema="public",
    )
    op.create_index("idx_pantry_import_idempotency_created",
                    "pantry_import_idempotency_records", ["created_at"], schema="public")
    op.execute("ALTER TABLE public.pantry_import_idempotency_records ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.pantry_import_idempotency_records FROM PUBLIC")
    for role in ("anon", "authenticated"):
        op.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '" + role + "') "
            "THEN REVOKE ALL ON TABLE public.pantry_import_idempotency_records FROM " + role + "; END IF; END $$;"
        ))


def downgrade():
    op.drop_index("idx_pantry_import_idempotency_created",
                  table_name="pantry_import_idempotency_records", schema="public")
    op.drop_table("pantry_import_idempotency_records", schema="public")
