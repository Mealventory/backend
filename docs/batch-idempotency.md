# Idempotent scan-review batch saves

The reviewed scanner sends confirmed items to `POST /api/v1/items/batch`.
The mobile review screen creates a unique `Idempotency-Key` for that submission
and **reuses the key when the request fails ambiguously** (timeout or lost
response). Editing, selecting, or removing review items starts a fresh operation
with a new key. Other callers remain unkeyed and retain the existing behavior.

```http
POST /api/v1/items/batch
Authorization: Bearer <verified-access-token>
X-Household-ID: <verified-household-uuid>
Idempotency-Key: scan-unique-operation-id
Content-Type: application/json

[{"name":"Milk","quantity":2,"unit":"bottles","storage_zone":"fridge"}]
```

The backend validates 16–128 ASCII characters (letters, digits, underscores,
and hyphens; first character must be alphanumeric). The database primary key
is **(household_id, authenticated_user_id, idempotency_key)**, so clients
cannot replay another user's or household's results just by guessing a key.
The SHA-256 hash of normalized Pydantic `ItemCreate` payloads is saved, not
the raw request body. Reusing the key with different items returns HTTP 409.

### Atomicity and concurrency

The first request inserts a unique claim row, inserts the inventory rows,
records inventory activity, saves the serialized successful response, and
commits everything in one database transaction. PostgreSQL's unique key
ensures simultaneous submissions wait for that transaction. The second
request returns the original 201 response (including the same item IDs)
without duplicating writes. A failed batch rolls back its claim and all
items, so a corrected retry can reuse the key. Ordinary unkeyed/manual
inserts do not use this table and remain unchanged.

Records persist in `batch_idempotency_records` until explicitly pruned or
the household is deleted (on-delete cascade). A `created_at` index supports
a future operational retention policy; removing old records can allow a
very late retry to create a new batch, so establish a retention guarantee
before enabling cleanup.

### Deployment

**Run the database migration before deploying keyed clients/backend.**
The API does not auto-migrate the database. With your deliberately selected
`ALEMBIC_DATABASE_URL` and appropriate backup, run:

```bash
python -m alembic upgrade head
python -m alembic current
```

Expected new revision: `20261022_0008`. Do not rerun the baseline on a
populated database or point migrations at a shared database accidentally.

### Verification

```bash
pytest -q tests/test_batch_idempotency.py
npm test
```

For disposable PostgreSQL 16 Docker integration, on a machine with Docker:

```bash
RUN_POSTGRES_TESTS=1 python -m pytest tests/test_batch_idempotency_postgres.py tests/test_alembic_postgres.py -v
```

The PostgreSQL tests never use your real `DATABASE_URL`.
Test a scan review in the app, simulate a timeout after a server commit, then
retry without editing; confirm one inventory batch exists. A changed payload
with the same key should fail with 409. Test unkeyed batch callers separately.

**Note:** The pending identical-item stacking PR (#118) also changes the batch
creation path. Re-run the test suite when that PR is merged or rebased so
idempotency replay correctly returns the first stacked response.
