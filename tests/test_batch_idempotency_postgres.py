"""Opt-in PostgreSQL concurrency checks on disposable test database only.

RUN_POSTGRES_TESTS=1 python -m pytest tests/test_batch_idempotency_postgres.py -v
"""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth_errors import AuthProblem
from app.schemas.household_inventory import ItemCreate
from app.schemas.user import UserOut
from app.services import household_service
from app.services.batch_idempotency_service import save_reviewed_batch_once
from tests.test_household_postgres import postgres_engine, A
from tests.test_init_db_postgres import pytestmark


@pytest.fixture
def pg_idempotency(postgres_engine):
    # The older scripts/init_db.sql fixture predates Alembic migrations;
    # declare the new tables here, matching the migration shape, on a
    # disposable database. Alembic tests independently verify upgrade head.
    with postgres_engine.begin() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS batch_idempotency_records (
                household_id uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
                user_id uuid NOT NULL,
                idempotency_key varchar(128) NOT NULL,
                request_hash varchar(64) NOT NULL,
                response_json text NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (household_id, user_id, idempotency_key)
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS household_activity_events (
                id uuid PRIMARY KEY,
                household_id uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
                actor_user_id uuid NOT NULL,
                actor_name varchar(120) NOT NULL,
                action varchar(40) NOT NULL,
                entity_type varchar(20) NOT NULL,
                entity_id uuid,
                item_name varchar(200) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """))
    yield postgres_engine


def test_simultaneous_same_key_commits_exactly_one_batch(pg_idempotency):
    engine = pg_idempotency
    with Session(engine) as db:
        home = household_service.create_household(db, A, "Idempotency concurrent")
    actor = UserOut(id=A, email="owner@example.com")
    key = "scan-" + uuid4().hex
    items = [ItemCreate(name="Rice", quantity="2", unit="kg", storage_zone="pantry")]

    def submit(_):
        with Session(engine) as db:
            return save_reviewed_batch_once(db, home.id, items, actor, key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(submit, range(2)))
    assert first == second
    assert len(first) == 1
    with engine.connect() as db:
        values = {"home": str(home.id)}
        assert db.execute(text("SELECT count(*) FROM inventory_items WHERE household_id=:home"), values).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM batch_idempotency_records WHERE household_id=:home"), values).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM household_activity_events WHERE household_id=:home"), values).scalar_one() == 1


def test_failed_transaction_releases_claim_for_next_postgres_request(pg_idempotency):
    engine = pg_idempotency
    with Session(engine) as db:
        home = household_service.create_household(db, A, "Idempotency rollback")
    actor = UserOut(id=A)
    key = "scan-" + uuid4().hex
    with Session(engine) as db:
        with pytest.raises(AuthProblem) as exc:
            save_reviewed_batch_once(db, home.id, [
                ItemCreate(name="Rice"),
                ItemCreate(name="Unknown storage", storage_location_id=uuid4()),
            ], actor, key)
        assert exc.value.status_code == 404
    with Session(engine) as db:
        saved = save_reviewed_batch_once(db, home.id, [ItemCreate(name="Bread")], actor, key)
        assert saved[0]["name"] == "Bread"
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM batch_idempotency_records WHERE household_id=:home"), {"home": str(home.id)}).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM inventory_items WHERE household_id=:home"), {"home": str(home.id)}).scalar_one() == 1
