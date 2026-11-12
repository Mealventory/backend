# Mealventory Backend

The backend has one FastAPI application: `app.main:app`. `main:app` imports
that same application, so either launch command exposes the same v1 API.

## Run locally

Use Python 3.11.9 and configure `.env` with `DATABASE_URL` and `AI_SERVICE_URL`.
Supabase access tokens authenticate requests. Configure `SUPABASE_URL` and
`SUPABASE_JWT_ALGORITHM`; HS256 also needs `SUPABASE_JWT_SECRET`. See
[authentication setup and rollout limitations](https://github.com/Mealventory/docs/blob/main/supabase-auth.md).
`OPENROUTER_API_KEY` and `OPENROUTER_MODEL` configure production recipe generation.
Recipe generation runs directly in the backend through OpenRouter; it does not call
`ai-services`. The provider request uses a 60-second timeout and provider/model
failures are returned to clients as safe 503/504 errors.

Create a local virtual environment instead of committing one to the repository:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
npm ci
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`. Both `.venv*/` and `node_modules/` are
ignored by Git and must be recreated locally from the checked-in dependency
manifests and lockfile.

Swagger UI: http://127.0.0.1:8000/docs
OpenAPI: http://127.0.0.1:8000/openapi.json
A checked-in copy is in the documentation repository: [openapi.json](https://github.com/Mealventory/docs/blob/main/openapi.json).

## Database migrations

Alembic owns structural database changes from Sprint 4 onward. Migration commands
require an explicit `ALEMBIC_DATABASE_URL`; they intentionally ignore the
application's `DATABASE_URL`. The FastAPI application does not run migrations
at startup.

For a clean database:

```sh
python -m alembic upgrade head
```

For an existing current-schema development database, first run the non-destructive
baseline checker, then stamp the baseline before upgrading:

```sh
python scripts/check_alembic_baseline.py
python -m alembic stamp 20261002_0001
python -m alembic upgrade head
```

See [database migration setup, macOS/Windows commands, downgrade guidance, and PostgreSQL smoke tests](docs/database-migrations.md).

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Liveness (not database readiness) |
| POST | `/api/v1/users/register` | Optional legacy profile sync |
| GET | `/api/v1/users/me` | Current user |
| POST | `/api/v1/households` | Create household and owner membership |
| POST | `/api/v1/households/join` | Join by invite code (rate limited) |
| GET | `/api/v1/households/me` | List your households |
| POST | `/api/v1/households/{household_id}/invite-code/rotate` | Owner-only invite code rotation/revocation |
| GET | `/api/v1/households/{household_id}/members` | List household members |
| PATCH, DELETE | `/api/v1/households/{household_id}/members/{user_id}` | Manage roles or remove/leave |
| GET, POST | `/api/v1/inventory/` | List or add inventory |
| DELETE | `/api/v1/inventory/{item_id}` | Delete owned item |
| POST | `/api/v1/scan/` | Scan and add inventory (rate limited) |
| POST | `/api/v1/scan/sample` | Optional development sample scan |
| GET | `/api/v1/recipes/` | Suggest recipes from inventory |
| POST | `/api/v1/food/predict-expiry/{food_id}` | Predict expiry |
| PUT | `/api/v1/notifications/device` | Register/transfer this user's Expo push token |
| POST | `/api/v1/notifications/device/remove` | Remove this user's Expo push token |
| POST | `/api/v1/notifications/jobs/expiry` | Protected daily expiry-alert job trigger |

The sample helper requires `ENABLE_SAMPLE_SCAN=true`. Keep it disabled in
production. It requires a Supabase token and verified `X-Household-ID`; persistence
can target only the authenticated user.

Household invite codes are reusable until an owner rotates them. Rotation immediately
invalidates the previous code without changing existing memberships. Automatic invite
code expiration is intentionally out of scope for now; owners explicitly rotate codes
when they need to revoke access.
The food predictor retains its existing response; its date attributes are not
mapped database columns, so it must not be treated as durable date persistence.

## API error contract

API errors use RFC 7807-style Problem Details with the
`application/problem+json` media type. Responses include stable `type`,
`title`, `status`, `detail`, and `instance` fields. Request validation
errors use status 422 and add an `errors` array containing only field location,
message, and validation type; submitted values are not echoed back. Provider-specific
safe recovery hints may appear as extension fields such as `code` and `action`.

The common documented error statuses are 400, 401, 403, 404, 409, 422, 429, 503,
and 504. Internal exception text, SQL errors, credentials, hostnames, bearer tokens,
and raw request payloads must never be exposed in public error responses.

## Expiry push notification job

Phones register Expo push tokens through `PUT /api/v1/notifications/device`.
Delivery is intentionally run by an external scheduler rather than an in-process
FastAPI timer. Configure a long random `NOTIFICATION_JOB_SECRET`, then have the
deployment scheduler call the job once each morning:

```sh
curl -X POST "https://YOUR_BACKEND/api/v1/notifications/jobs/expiry" \
  -H "X-Notification-Job-Secret: YOUR_LONG_RANDOM_SECRET"
```

Use `?dry_run=true` to inspect counts without contacting Expo. The job selects
only active inventory dated today through two days from today, groups items by
household, enforces same-calendar-day idempotency via
`expiry_notification_dispatches`, and sends one grouped alert to every registered
device belonging to a current household member. Expired, undated, consumed, and
discarded items are not included. Expo tokens reported as `DeviceNotRegistered`
are removed, and accepted push tickets are logged for verification.

To check Expo delivery receipts for previously dispatched expiry notifications
and remove asynchronously flagged `DeviceNotRegistered` tokens, schedule a
follow-up call roughly 15–30 minutes after the daily dispatch:

```sh
curl -X POST "https://YOUR_BACKEND/api/v1/notifications/jobs/receipts" \
  -H "X-Notification-Job-Secret: YOUR_LONG_RANDOM_SECRET"
```

Mealventory does not currently store a timezone preference per user. Schedule
the endpoint for 08:00 in the deployment's intended household/demo timezone;
true per-user 08:00 delivery requires adding timezone data first. If Expo push
access-token security is enabled for the EAS project, also configure
`EXPO_PUSH_ACCESS_TOKEN`.

## Structure and tests

`app/api/v1/` contains HTTP adapters; `app/services/` contains auth, inventory,
scan orchestration, AI transport, expiry and recipe logic. Database sessions use
one dependency in `app/dependencies/database.py`.

```sh
python -m pytest tests/
```

Ordinary tests use in-memory SQLite and mocked authentication/AI, never the
configured live database or paid AI APIs. Opt-in PostgreSQL/Alembic smoke tests
create disposable PostgreSQL 16 Docker databases and explicitly ignore
`DATABASE_URL`. They cover current v1 routes, retired route 404s, migration
upgrade/downgrade behavior, and OpenAPI contract checks.

## Continuous integration

GitHub Actions runs `.github/workflows/backend-ci.yml` for every pull request and every push to `main`. The required CI path rejects committed `.venv311/` and `node_modules/` directories, uses Python 3.11, installs `requirements-dev.txt`, runs the ordinary offline pytest suite, repeats the OpenAPI contract regression test with a focused log, and verifies that the backend Docker image builds.

The normal CI jobs do not use production credentials, Supabase production access, Google APIs, paid AI providers, or the shared database. The test fixtures provide local/mocked configuration only.

PostgreSQL integration tests are intentionally opt-in because they start disposable Docker infrastructure. To run them in GitHub Actions, open **Actions -> Backend CI -> Run workflow**, enable **Run the disposable PostgreSQL integration suite**, and start the workflow. That job sets only `RUN_POSTGRES_TESTS=1`; the tests create temporary PostgreSQL 16 containers with generated local credentials and explicitly avoid `DATABASE_URL`.

See [the retirement audit](https://github.com/Mealventory/docs/blob/main/legacy-retirement.md) for migration notes.
See [household management](https://github.com/Mealventory/docs/blob/main/household-management.md) for permissions and setup.
Shared inventory and analytics remain separate features;
[the target architecture](https://github.com/Mealventory/docs/blob/main/target-architecture.md) is not the current contract.
