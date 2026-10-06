# Database migrations

Alembic is the migration history for Mealventory database structure from Sprint 4 onward. The FastAPI app **does not** run migrations automatically at startup.

The migration CLI intentionally reads only `ALEMBIC_DATABASE_URL`. It does not fall back to the application's `DATABASE_URL`, so having a production/shared backend `.env` file present is not enough to target that database accidentally.

## Clean database

Point `ALEMBIC_DATABASE_URL` at a new PostgreSQL database, then upgrade to the latest revision.

### macOS / Linux

```sh
export ALEMBIC_DATABASE_URL='postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME'
python -m alembic upgrade head
python -m alembic current
```

### Windows PowerShell

```powershell
$env:ALEMBIC_DATABASE_URL = 'postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME'
python -m alembic upgrade head
python -m alembic current
```

Revision `20261002_0001` is an immutable snapshot of the current shared-household structure, including the later household stores, saved recipes, and recipe-completion tables that were previously introduced with separate SQL scripts. Revision `20261002_0002` is a small reversible follow-up index used to prove normal upgrade/downgrade behavior.

Supabase RLS remains an explicit security bootstrap in `scripts/enable_rls.sql`. Alembic owns structural evolution; do not rerun the one-time RLS bootstrap against a database that already has policies without reviewing it first.

## Existing development database

Do **not** run the baseline upgrade on a populated database that already has the current tables, because the baseline intentionally creates objects and should fail rather than overwrite them.

First back up the database. Then point `ALEMBIC_DATABASE_URL` at that specific development database and run:

```sh
python scripts/check_alembic_baseline.py
```

The checker verifies the current baseline tables, important columns, enums, and update trigger function without changing data. If it passes, record the baseline without replaying its DDL:

```sh
python -m alembic stamp 20261002_0001
python -m alembic upgrade head
python -m alembic current
```

`stamp` only writes Alembic's version marker. It does not create, drop, or alter application tables. The following `upgrade head` applies only revisions after the baseline.

If the checker reports that `household_saved_recipes` or `household_recipe_completions` is missing, the database is not at the baseline yet. Do not stamp it as current; bring that development database to the expected schema first.

## Upgrade and downgrade

Apply all pending migrations:

```sh
python -m alembic upgrade head
```

Inspect current and historical revisions:

```sh
python -m alembic current
python -m alembic history
```

Roll back only the sample follow-up revision:

```sh
python -m alembic downgrade 20261002_0001
```

Reapply it:

```sh
python -m alembic upgrade head
```

Do not use `python -m alembic downgrade base` on a shared or populated database. The baseline downgrade intentionally drops the Mealventory schema and exists only so disposable migration tests can prove reversibility.

## Creating future revisions

Create a revision:

```sh
python -m alembic revision -m "describe schema change"
```

Write the `upgrade()` and `downgrade()` operations explicitly and review both directions before applying them.

Alembic is connected to the maintained SQLAlchemy model metadata where practical, but several legacy model classes still do not mirror the household PostgreSQL DDL. For that reason `--autogenerate` is blocked by default. Do not enable it casually. If model parity is completed later, the guard can be revisited.

## Migration tests

The PostgreSQL migration tests never read `DATABASE_URL`. They create a disposable PostgreSQL 16 Docker container on an ephemeral loopback port and pass its generated URL through `ALEMBIC_DATABASE_URL`.

Run them explicitly:

```sh
RUN_POSTGRES_TESTS=1 python -m pytest tests/test_alembic_postgres.py -v
```

On Windows PowerShell:

```powershell
$env:RUN_POSTGRES_TESTS = '1'
python -m pytest tests/test_alembic_postgres.py -v
```

The smoke suite covers a clean upgrade to `head`, a downgrade/reapply of the follow-up revision, and the safe check -> stamp -> upgrade flow for a populated current-schema database.
