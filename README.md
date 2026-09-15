# Mealventory Backend

The backend has one FastAPI application: `app.main:app`. `main:app` imports
that same application, so either launch command exposes the same v1 API.

## Run locally

Use Python 3.11.9 and configure `.env` with `DATABASE_URL` and `AI_SERVICE_URL`.
Firebase credentials are required for authenticated requests. `OPENROUTER_API_KEY`
and `OPENROUTER_MODEL` configure the recipe fallback. Existing Supabase API keys
may remain in `.env`, but the retired prototype client is no longer loaded.

```sh
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs
OpenAPI: http://127.0.0.1:8000/openapi.json
A checked-in copy is in [docs/openapi.json](docs/openapi.json).

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Liveness (not database readiness) |
| POST | `/api/v1/users/register` | Sync Firebase user |
| GET | `/api/v1/users/me` | Current user |
| GET, POST | `/api/v1/inventory/` | List or add inventory |
| DELETE | `/api/v1/inventory/{item_id}` | Delete owned item |
| POST | `/api/v1/scan/` | Scan and add inventory |
| POST | `/api/v1/scan/sample` | Optional development sample scan |
| GET | `/api/v1/recipes/` | Suggest recipes from inventory |
| POST | `/api/v1/food/predict-expiry/{food_id}` | Predict expiry |

The sample helper requires `ENABLE_SAMPLE_SCAN=true`. Keep it disabled in
production. It retains its existing development-only user-ID persistence option.
The food predictor retains its existing response; its date attributes are not
mapped database columns, so it must not be treated as durable date persistence.

## Structure and tests

`app/api/v1/` contains HTTP adapters; `app/services/` contains auth, inventory,
scan orchestration, AI transport, expiry and recipe logic. Database sessions use
one dependency in `app/dependencies/database.py`.

```sh
python -m pytest tests/
```

Tests use in-memory SQLite and mocked authentication/AI, never the configured
live database or paid AI APIs. They cover current v1 routes, retired route 404s,
and compare OpenAPI schemas and operation IDs against the pre-cleanup contract.

See [the retirement audit](docs/legacy-retirement.md) for migration notes.
Households, analytics, Supabase JWT migration and RLS remain future features;
[the target architecture](docs/target-architecture.md) is not the current contract.
