"""Validate an existing database before stamping the Alembic baseline.

This command intentionally reads ALEMBIC_DATABASE_URL only. It never falls back
to the application's DATABASE_URL.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect, text


BASELINE_REVISION = "20261002_0001"
REQUIRED_TABLES = {
    "households",
    "household_members",
    "storage_locations",
    "foods",
    "inventory_items",
    "recipes",
    "recipe_ingredients",
    "shopping_list_items",
    "household_stores",
    "device_push_tokens",
    "household_saved_recipes",
    "household_recipe_completions",
}
REQUIRED_COLUMNS = {
    "inventory_items": {"household_id", "food_id", "quantity", "unit", "status"},
    "household_stores": {"household_id", "name", "website_url", "sort_order"},
    "household_recipe_completions": {
        "household_id",
        "completion_id",
        "fingerprint",
        "result",
    },
}


def fail(message: str) -> None:
    print(f"Baseline check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    database_url = os.getenv("ALEMBIC_DATABASE_URL")
    if not database_url:
        fail(
            "ALEMBIC_DATABASE_URL is required. DATABASE_URL is intentionally ignored."
        )

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        existing = set(inspector.get_table_names(schema="public"))
        missing_tables = sorted(REQUIRED_TABLES - existing)
        if missing_tables:
            fail("missing tables: " + ", ".join(missing_tables))

        for table, expected in REQUIRED_COLUMNS.items():
            columns = {
                column["name"]
                for column in inspector.get_columns(table, schema="public")
            }
            missing = sorted(expected - columns)
            if missing:
                fail(f"{table} is missing columns: {', '.join(missing)}")

        with engine.connect() as connection:
            enum_count = connection.execute(
                text(
                    "SELECT count(*) FROM pg_type "
                    "WHERE typnamespace='public'::regnamespace "
                    "AND typname IN ('member_role','storage_zone','item_status')"
                )
            ).scalar_one()
            if enum_count != 3:
                fail("expected member_role, storage_zone, and item_status enums")

            trigger_function = connection.execute(
                text(
                    "SELECT count(*) FROM pg_proc "
                    "WHERE pronamespace='public'::regnamespace "
                    "AND proname='update_updated_at_column'"
                )
            ).scalar_one()
            if trigger_function != 1:
                fail("public.update_updated_at_column() is missing")

        print(
            "Baseline check passed. Existing schema matches the structural "
            f"requirements for {BASELINE_REVISION}."
        )
        print(
            f"Next: python -m alembic stamp {BASELINE_REVISION} && "
            "python -m alembic upgrade head"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
