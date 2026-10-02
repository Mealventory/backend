"""Alembic smoke tests against disposable PostgreSQL 16 only.

RUN_POSTGRES_TESTS=1 python -m pytest tests/test_alembic_postgres.py -v

These tests create an isolated Docker database on an ephemeral loopback port.
They deliberately remove DATABASE_URL from subprocess environments so a
configured shared/live database cannot be selected accidentally.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from tests.test_init_db_postgres import docker


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 to run isolated Docker PostgreSQL 16 tests",
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "20261002_0001"
HEAD = "20261002_0004"
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


@pytest.fixture(scope="module")
def postgres_server():
    name = "mealventory-alembic-test-" + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    result = docker(
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--publish",
        "127.0.0.1::5432",
        "-e",
        "POSTGRES_PASSWORD=" + password,
        "postgres:16",
    )
    assert result.returncode == 0, result.stderr

    try:
        for _ in range(60):
            if docker("exec", name, "pg_isready", "-U", "postgres").returncode == 0:
                break
            time.sleep(0.5)
        else:
            pytest.fail("PostgreSQL startup timed out")

        port_result = docker("port", name, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = int(port_result.stdout.strip().rsplit(":", 1)[1])
        yield name, password, port
    finally:
        assert docker("stop", name).returncode == 0


@pytest.fixture
def database_url(postgres_server):
    container, password, port = postgres_server
    database = "alembic_" + uuid.uuid4().hex
    result = docker("exec", container, "createdb", "-U", "postgres", database)
    assert result.returncode == 0, result.stderr

    url = URL.create(
        "postgresql+psycopg2",
        username="postgres",
        password=password,
        host="127.0.0.1",
        port=port,
        database=database,
    ).render_as_string(hide_password=False)

    try:
        yield url
    finally:
        result = docker("exec", container, "dropdb", "-U", "postgres", database)
        assert result.returncode == 0, result.stderr


def command_env(database_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["ALEMBIC_DATABASE_URL"] = database_url
    return env


def run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=command_env(database_url),
        text=True,
        capture_output=True,
        timeout=180,
    )


def run_baseline_check(database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_alembic_baseline.py"],
        cwd=ROOT,
        env=command_env(database_url),
        text=True,
        capture_output=True,
        timeout=60,
    )


def test_clean_database_upgrades_to_current_schema(database_url):
    result = run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names(schema="public"))
        assert REQUIRED_TABLES <= tables
        assert "alembic_version" in tables

        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert connection.execute(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE schemaname='public' "
                    "AND indexname='idx_recipe_completions_household_created'"
                )
            ).scalar_one() == 1
    finally:
        engine.dispose()


def test_followup_migration_can_downgrade_and_reapply(database_url):
    assert run_alembic(database_url, "upgrade", "head").returncode == 0

    downgraded = run_alembic(database_url, "downgrade", BASELINE)
    assert downgraded.returncode == 0, downgraded.stderr

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == BASELINE
            assert connection.execute(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE schemaname='public' "
                    "AND indexname='idx_recipe_completions_household_created'"
                )
            ).scalar_one() == 0
    finally:
        engine.dispose()

    upgraded = run_alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr


def test_existing_current_schema_can_be_checked_stamped_and_upgraded(database_url):
    engine = create_engine(database_url)
    try:
        # The legacy SQL files own their own BEGIN/COMMIT blocks, so execute
        # them through a DBAPI cursor rather than nesting them inside
        # SQLAlchemy's transaction context.
        raw = engine.raw_connection()
        try:
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute(
                    (
                        ROOT
                        / "alembic"
                        / "sql"
                        / "20261002_0001_current_household_baseline.sql"
                    ).read_text()
                )
                cursor.execute(
                    "INSERT INTO households(id,name,created_by,invite_code) "
                    "VALUES ('00000000-0000-0000-0000-000000000001', "
                    "'Existing household', "
                    "'10000000-0000-0000-0000-000000000001', 'BASE01')"
                )
        finally:
            raw.close()
    finally:
        engine.dispose()

    checked = run_baseline_check(database_url)
    assert checked.returncode == 0, checked.stderr
    assert "Baseline check passed" in checked.stdout

    stamped = run_alembic(database_url, "stamp", BASELINE)
    assert stamped.returncode == 0, stamped.stderr
    upgraded = run_alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT name FROM households WHERE invite_code='BASE01'")
            ).scalar_one() == "Existing household"
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == HEAD
    finally:
        engine.dispose()
