"""Keyed scan batch saves retry safely without changing legacy/manual behavior."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.test_household_inventory import inventory_api, HOME, OTHER, MEMBER, OUTSIDER


@pytest.fixture
def keyed_api(inventory_api):
    client, identity, engine = inventory_api
    # SQLite unit fixture mirrors the Alembic table; Postgres concurrency and
    # migration tests exercise the real database constraint independently.
    with engine.begin() as db:
        db.execute(text("""
            CREATE TABLE batch_idempotency_records (
                household_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (household_id, user_id, idempotency_key)
            )
        """))
    yield client, identity, engine


def _items(name="Rice"):
    return [{"name": name, "quantity": 2, "unit": "kg", "storage_zone": "pantry"}]


def _headers(household=HOME, key="review-batch-1234567890"):
    return {"X-Household-ID": household, "Idempotency-Key": key}


def _count(db, table, household=HOME):
    return db.execute(
        text(f"SELECT count(*) FROM {table} WHERE household_id=:h"), {"h": household}
    ).scalar_one()


def test_replay_after_ambiguous_response_creates_no_more_inventory(keyed_api):
    client, _, engine = keyed_api
    first = client.post("/api/v1/items/batch", headers=_headers(), json=_items())
    second = client.post("/api/v1/items/batch", headers=_headers(), json=_items())
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    assert first.json() == second.json()
    assert first.json()[0]["quantity"] == "2"
    with engine.connect() as db:
        assert _count(db, "inventory_items") == 1
        assert _count(db, "batch_idempotency_records") == 1
        assert _count(db, "household_activity_events") == 1


def test_changed_payload_under_same_key_is_rejected(keyed_api):
    client, _, engine = keyed_api
    assert client.post("/api/v1/items/batch", headers=_headers(), json=_items()).status_code == 201
    changed = client.post("/api/v1/items/batch", headers=_headers(), json=_items("Pasta"))
    assert changed.status_code == 409
    assert "different items" in changed.json()["detail"]
    with engine.connect() as db:
        assert _count(db, "inventory_items") == 1


def test_idempotency_scoped_by_verified_household_and_user(keyed_api):
    client, identity, engine = keyed_api
    first = client.post("/api/v1/items/batch", headers=_headers(), json=_items())
    identity["id"] = MEMBER
    second = client.post("/api/v1/items/batch", headers=_headers(), json=_items())
    identity["id"] = OUTSIDER
    third = client.post("/api/v1/items/batch", headers=_headers(OTHER), json=_items())
    assert all(r.status_code == 201 for r in (first, second, third))
    assert len({first.json()[0]["id"], second.json()[0]["id"], third.json()[0]["id"]}) == 3
    # Repeating someone else's key does not bypass authorization.
    denied = client.post("/api/v1/items/batch", headers=_headers(HOME), json=_items())
    assert denied.status_code == 403
    with engine.connect() as db:
        assert _count(db, "batch_idempotency_records", HOME) == 2
        assert _count(db, "batch_idempotency_records", OTHER) == 1


def test_failed_atomic_batch_releases_key_for_safe_retry(keyed_api):
    client, _, engine = keyed_api
    invalid = _items() + [{
        "name": "Bad zone", "storage_location_id": str(uuid4()),
    }]
    rejected = client.post("/api/v1/items/batch", headers=_headers(), json=invalid)
    assert rejected.status_code == 404, rejected.text
    with engine.connect() as db:
        assert _count(db, "inventory_items") == 0
        assert _count(db, "batch_idempotency_records") == 0
        assert _count(db, "household_activity_events") == 0
    retry = client.post("/api/v1/items/batch", headers=_headers(), json=_items("Oats"))
    assert retry.status_code == 201, retry.text
    assert retry.json()[0]["name"] == "Oats"


def test_invalid_key_and_unkeyed_legacy_batch(keyed_api):
    client, _, engine = keyed_api
    assert client.post(
        "/api/v1/items/batch", headers=_headers(key="short"), json=_items()
    ).status_code == 400
    for _ in range(2):
        assert client.post(
            "/api/v1/items/batch", headers={"X-Household-ID": HOME}, json=_items()
        ).status_code == 201
    with engine.connect() as db:
        assert _count(db, "inventory_items") == 2
        assert _count(db, "batch_idempotency_records") == 0
