# Issue #29 — initial PostgreSQL 16 schema

`scripts/init_db.sql` creates the household-based schema in a **clean** PostgreSQL
16 database. It runs in one transaction, does not drop objects, and intentionally
fails on a second run or a conflicting pre-existing table. An error rolls back
all changes from that run. There are no extensions or Supabase-only dependencies.

## Execute on an empty development database

Use an explicitly selected development database, not the existing backend `.env`
connection. Supply credentials through your normal secure PostgreSQL mechanism.

```sh
psql -X --set ON_ERROR_STOP=1 --dbname "$EMPTY_DEV_DATABASE_URL" --file scripts/init_db.sql
```

Do not run this on the current Mealventory database: existing `foods` and
`inventory_items` have incompatible integer IDs and per-user ownership. This is
an initial schema, not an in-place data migration. No existing data was migrated.
The current SQLAlchemy models and API still require the older schema. Application
model migration, existing-data conversion, JWT integration and rollout need
separate coordinated work before the backend can use this schema.

## Design decisions

- UUID primary keys default to PostgreSQL's built-in `gen_random_uuid()`.
  Membership uses `(household_id, user_id)` as its composite primary key.
- `member_role`: `owner`, `admin`, `member`.
- `storage_zone`: `pantry`, `fridge`, `freezer`, `spicerack`, matching the frontend.
- `item_status`: `active`, `consumed`, `discarded`. These are lifecycle states,
  not the frontend's computed freshness/urgency labels.
- `foods` is a global reference catalogue; recipes, storage, inventory and
  shopping data are household-owned. Ingredient rows carry `household_id` too.
- Composite foreign keys prevent inventory from referencing another household's
  storage location and ingredients from referencing another household's recipe.
- User IDs (`created_by`, memberships and device tokens) are external UUID
  identity references. Plain PostgreSQL has no `auth.users`, and the issue does
  not request a separate users table. Supabase deployment should add auth-user
  foreign keys once identity integration is defined; nonexistent external users
  are not rejected by this standalone migration.
- Membership role cardinality (such as always retaining an owner), invite code
  generation/rotation, and authorization belong to subsequent application work.
  Invite codes are nullable until generated, unique when present, and exactly six
  uppercase ASCII letters/digits. No weak automatic code generator is added.
- Device tokens are user-owned, globally unique, and are not tied to one household
  because a user may belong to multiple households.
- Amounts use exact decimal quantities. Inventory permits zero; recipe ingredients
  and shopping quantities must be positive. NaN, negative durations, blank names
  and invalid enum values are rejected. Expiry may precede purchase to support
  recording already-expired food; validity is not inferred from these dates.
- Deleting a household cascades through its owned data and membership. Deleting
  an in-use food or storage location fails to protect references. Deleting a
  household does not delete global foods or user device registrations.
- All nine tables have `created_at` and `updated_at` timestamps. BEFORE UPDATE
  triggers replace caller-supplied `updated_at` with `clock_timestamp()`, including
  multiple writes in a transaction. They do not rewrite `created_at` automatically.
- Required compound indexes are `idx_inventory_tenant` on
  `(household_id, status, expiry_date)` and `idx_household_members` on
  `(user_id, household_id)`. Additional indexes support foreign-key lookups and
  tenant shopping/recipe queries.

## Security boundary

Foreign keys enforce relational consistency, not permission to read or write
another household. This migration does not implement RLS policies or application
roles/grants; #41 must provide those before exposing these tables to Supabase
clients. No production deployment or billing action is part of this work.

## Reproduce the PostgreSQL 16 acceptance tests

With Docker running and development requirements installed:

```sh
RUN_POSTGRES_TESTS=1 python -m pytest tests/test_init_db_postgres.py -v
```

The test module creates a uniquely named `postgres:16` container with no network,
no published ports and no mounted host database volume. It uses Docker exec and
temporary databases, never `DATABASE_URL` or Supabase. It stops/removes its own
container afterward. Docker downloads the image if it is not already present.
Authentication is trusted only inside this disposable, network-isolated container.
The module is skipped during ordinary offline test runs unless explicitly enabled.

Coverage includes: all nine tables and primary keys; the three enums; compound
index column order; a connected seed graph; defaults; timestamp triggers on all
tables; cross-household and missing-reference rejection; invalid values;
duplicate membership/token rejection; deletion cascades/reference protection;
a nondestructive failed rerun; and rollback after a mid-migration conflict.
