from __future__ import annotations

from dotenv import load_dotenv

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.base import Base

# Import only maintained model mappings. Several legacy models intentionally do
# not mirror the household PostgreSQL DDL yet, so autogeneration remains opt-in.
from app.models.household import Household  # noqa: F401
from app.models.household_member import HouseholdMember  # noqa: F401
from app.models.household_store import HouseholdStore  # noqa: F401
from app.models.push_token import PushToken  # noqa: F401
from app.models.saved_recipe import SavedRecipe  # noqa: F401
from app.models.shopping import ShoppingListItem  # noqa: F401

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migration commands intentionally do not fall back to the application's
# DATABASE_URL. This prevents an accidental migration of a shared/live database
# just because the backend .env file is present.
database_url = os.getenv("ALEMBIC_DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "ALEMBIC_DATABASE_URL is required for migration commands. "
        "DATABASE_URL is intentionally ignored."
    )

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata

if (
    getattr(config.cmd_opts, "autogenerate", False)
    and os.getenv("ALLOW_ALEMBIC_AUTOGENERATE") != "1"
):
    raise RuntimeError(
        "Alembic autogenerate is disabled until all household SQLAlchemy "
        "mappings match the PostgreSQL schema. Write revisions explicitly, or "
        "set ALLOW_ALEMBIC_AUTOGENERATE=1 only after reviewing the diff."
    )


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
