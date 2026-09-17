# Issue #44: household inventory updates

These endpoints extend the current household API at `/api/v1/items`. The older `/api/v1/inventory/` routes retain their existing per-user contracts; clients should use `/items` for the shared UUID-based inventory. Do not mix IDs between those APIs.

Every request requires `Authorization: Bearer <Supabase access token>` and `X-Household-ID: <UUID>`. Owners, admins, and members can manage their household's inventory. Outsiders receive 403; IDs belonging to another household receive 404 without exposing that household's data.

| Action | Request | Result |
| --- | --- | --- |
| Edit an active item | `PATCH /api/v1/items/{id}` | 200, updated item |
| Mark consumed | `POST /api/v1/items/{id}/consume` | 200, retained row with `consumed` status |
| Mark discarded | `POST /api/v1/items/{id}/discard` | 200, retained row with `discarded` status |
| Add confirmed scan items atomically | `POST /api/v1/items/batch` | 201, array of created items |
| Filter items | `GET /api/v1/items?status=active&zone=fridge&expiring_days=3&search=milk` | 200, matching items |

## Editing

Example body: `{"quantity":2.5,"unit":"kg","expiry_date":"2026-10-01"}`.

Supported fields: `quantity`, `unit`, `expiry_date`, `storage_location_id`. Omitted fields are preserved. Explicit null clears the expiration date or storage location. Quantity must be positive with at most three decimal places; quantity and unit cannot be null. Empty patches and unknown fields return 422. Storage locations must belong to the same household. Edits do not alter the shared food catalogue name/category.

## Status and history

Transitions are `active → consumed` or `active → discarded`. The record and quantity remain available for later analytics. Repeating the same final action returns 200 without changing it again. Conflicting terminal actions or editing a non-active item return 409. Concurrent conflicting transitions allow only one winner.

`expired` is not a database status: expiration remains a date condition. The user-facing label “wasted” may map to `discarded`. Existing hard DELETE behavior is preserved for backwards compatibility; consumption/discard buttons should call the new status endpoints instead.

## Filters and batches

The default list remains active items. `status` accepts active/consumed/discarded. `zone` accepts pantry/fridge/freezer/spicerack. `expiring_days` accepts 0–3650 and includes overdue items up to the cutoff date; unknown dates are excluded. `search` is a case-insensitive literal substring, so `%` and `_` are not wildcards.

A batch body is an array of 1–100 existing ItemCreate objects. All insertions commit once; validation, an invalid household storage location, or a database error leaves no partial items or food records. This endpoint accepts reviewed items, not images.

## Frontend handoff and validation

Issue frontend #8 can connect the edit/consume/discard controls to these endpoints. The current pantry already refreshes active inventory, so terminal-status items disappear on subsequent refreshes. This backend change does not add frontend buttons.

No schema migration is required for the existing `init_db.sql` schema. Its updated_at trigger runs on edits and status changes. Do not rerun the clean-database initialization script on a populated database.

Tests cover membership, cross-household isolation, patch validation/null handling, six-item batches, transaction rollback, filtering, retained status history, and idempotent/conflicting actions. The opt-in PostgreSQL test also checks the actual updated_at trigger and concurrent transitions:

```bash
python -m pytest tests/ -q
RUN_POSTGRES_TESTS=1 python -m pytest tests/test_household_inventory_postgres.py -q
```

PostgreSQL tests use disposable Docker containers, never the configured application database.
