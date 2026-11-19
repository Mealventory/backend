"""Household meal plans with revision tombstones and retry-safe imports.

Revision ID: 20261119_0009
Revises: 69b9c45b9a94
"""
from alembic import op
import sqlalchemy as sa

revision = "20261119_0009"
down_revision = "69b9c45b9a94"
branch_labels = None
depends_on = None


def _secure_table(name):
    op.execute(f"ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON TABLE public.{name} FROM PUBLIC")
    # Bare PostgreSQL test instances may not have Supabase roles.
    for role in ("anon", "authenticated"):
        op.execute(sa.text(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '" + role + "') "
            "THEN REVOKE ALL ON TABLE public." + name + " FROM " + role + "; END IF; END $$;"
        ))


def upgrade():
    op.create_table(
        "household_meal_plan_slots",
        sa.Column("household_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(10), nullable=False),
        sa.Column("recipe_snapshot", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("slot IN ('lunch','dinner')", name="ck_meal_plan_slot"),
        sa.CheckConstraint("revision > 0", name="ck_meal_plan_revision"),
        sa.PrimaryKeyConstraint("household_id", "plan_date", "slot"),
        schema="public",
    )
    op.create_table(
        "household_meal_plan_imports",
        sa.Column("household_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("import_key", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("household_id", "user_id", "import_key"),
        schema="public",
    )
    for table in ("household_meal_plan_slots", "household_meal_plan_imports"):
        _secure_table(table)


def downgrade():
    op.drop_table("household_meal_plan_imports", schema="public")
    op.drop_table("household_meal_plan_slots", schema="public")
