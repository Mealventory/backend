# Issue #61: route retirement audit

## Decision and client compatibility

The old root `main.py` created a separate Supabase/PostgREST prototype app.
The maintained app is `app/main.py`, using Firebase authentication and SQLAlchemy.
Both launch modules now expose the exact same app. Do not deploy this change to
clients still using the prototype URLs without coordinating their migration.

The checked local frontend `app/` and `src/` contained no backend HTTP calls.
The manual scan script uses `/api/v1/scan`, which is retained. This local audit
cannot establish whether external or unpublished clients still use old URLs.
Every existing v1 URL, HTTP method, operation ID, request schema and response
schema is preserved by a frozen OpenAPI contract regression test.

## Retired surface

| Prototype routes | Disposition |
| --- | --- |
| `/api/v0/*` | Never registered in this checkout; continue returning 404 |
| `/inventory/*` | Removed; migrate to v1 inventory, adapting auth and payloads |
| `/food-items/*` | Removed; no equivalent general food-catalog CRUD in current v1 |
| `/scan/*`, including `/scan/scan/normalize` | Removed; current v1 scanning delegates to AI service |
| `/recipes/*`, including `/recipes/generate` and ingredient editing | Removed; v1 suggestions retained; CRUD has no drop-in replacement |
| `/health/*` | Removed; `/` provides liveness only, no database check |
| root test router | Never registered; removed |

These APIs had different data models and auth. They are deliberately not
redirected to v1, which would silently misinterpret client requests. Only
launch-command compatibility is retained for `main:app`; prototype HTTP clients
must migrate. Removed source remains recoverable from Git history.

## Code removed or moved

Removed root `api/`, `core/`, `schemas/`, `services/` and `utils/` after checking
imports. The one active root-service dependency, OpenRouter recipe generation,
was moved into `app/services/recipe_ai_service.py` first. No prototype Supabase
client or Google Vision credential loader runs when importing either app.

Removed the empty, unregistered v1 auth router; unused `FoodOut` and `UserCreate`
schemas; unused vision wrapper; unused freezer-keyword helper; and duplicate
expiry helpers from the Food ORM model. All three active ORM models remain.
The duplicate database-session dependency was consolidated.

The Alembic directory had no revision files and `target_metadata = None`; only
that unused scaffold and its placeholder config were removed. No live migration,
database table or row was changed. The schema migration work in #29 should add
a deliberately configured migration tree.

The manual `test_scan.py` script and standalone training scripts/data remain:
they are explicit developer tools, not imported prototype routes. Installed
virtual environments and vendored Node files are outside this cleanup's scope.

## Module names and behavior

Keep `users.py`, `inventory.py`, `scan.py`, `recipes.py` and `food.py` to preserve
current operation IDs and client URLs. The issue's proposed `auth.py`, `items.py`,
`households.py`, `scanner.py` and `analytics.py` names are not used to invent
unimplemented features or rename the published API. Business logic now lives in
services; HTTP adapters keep validation, dependencies and routing declarations.

During extraction, the upload scan path was found to pass a list to a helper
expecting item counts. It now counts detections before saving; a regression test
verifies two duplicate detections produce two inventory rows for the caller.

Known pre-existing limitations are retained: sample persistence reports zero
stored count, food prediction does not map dates to persistent columns, Firebase
remains the active v1 auth system, and the development sample persistence route
is not an authenticated production ingestion API. Address those in their own
features rather than silently changing contracts during retirement.

## Validation

Run `python -m pytest tests/`. Tests cover both entry points, old route 404s,
OpenAPI contract parity, user registration/authentication, inventory isolation,
scan upload and preview, recipe suggestions, and food prediction. Services and
SQLite are isolated; live authentication and production schema compatibility
are not claimed by these tests.
