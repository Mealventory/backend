> Future design, not the current API contract. See ../README.md.

# Mealventory Core Backend: Target Final State & Purpose

## 1. Purpose of the Repository
The `backend` repository is the centralized application engine and data layer for **Mealventory**. Built with **FastAPI (Python 3.11+)**, **Pydantic v2**, and **PostgreSQL (with Supabase RLS)**, it enforces multi-tenant household boundary isolation, orchestrates the inventory lifecycle, powers the smart recipe matching algorithm, interfaces with the AI microservice, and dispatches proactive expiration alerts.

### Key Functional Responsibilities:
- **Tenant Isolation & Security**: Provide strict multi-tenant boundary enforcement where all inventory, storage locations, and recipes belong to a `household`, verified at the database layer via PostgreSQL Row Level Security (RLS) and at the application layer via JWT authentication.
- **Inventory Lifecycle & Audit**: Manage CRUD operations, batch ingestions from OCR/vision, shelf-life calculation overrides, status transitions (`active` -> `consumed` | `discarded`), and consumption velocity tracking.
- **Smart Recipe Recommendation Engine**: Compute inventory-to-recipe ingredient matching scores in sub-50ms, applying dynamic boost multipliers for items expiring within 48 hours.
- **Automated Expiration Alert System**: Run scheduled background jobs to evaluate items approaching expiration and broadcast grouped alerts via Expo Push Notification services.
- **AI Service Gateway & Circuit Breaker**: Relay images and scan requests to `ai-services` asynchronously, handling timeouts, fallbacks, and payload normalization.

---

## 2. Target Architecture & Final Structure

### Architectural Pattern
Adheres to **Clean Architecture / Hexagonal Architecture** principles, maintaining strict separation of concerns across presentation, domain, and data access layers:

```
backend/
├── app/
│   ├── api/                          # FastAPI Route Controllers (Grouped by domain)
│   │   ├── v1/
│   │   │   ├── auth.py               # Supabase Auth sync & user profile endpoints
│   │   │   ├── households.py         # Household CRUD, invite codes, member management
│   │   │   ├── inventory.py          # Inventory CRUD, batch add, mark consumed/discarded
│   │   │   ├── scan.py               # Proxy to AI services with circuit breaker
│   │   │   ├── recipes.py            # Recipe suggestions, matching algorithms, "cook meal"
│   │   │   ├── shopping.py           # Shopping list management & "move to pantry"
│   │   │   ├── notifications.py      # Device push token registration & preferences
│   │   │   └── health.py             # Liveness & readiness probes
│   │   └── router.py                 # Unified API v1 router
│   │
│   ├── core/                         # Cross-cutting infrastructure concerns
│   │   ├── config.py                 # Pydantic Settings (Twelve-Factor environment config)
│   │   ├── security.py               # JWT verification & Supabase Auth token decoding
│   │   ├── dependencies.py           # FastAPI DI (get_db, get_current_user, get_household)
│   │   ├── exceptions.py             # Global exception handlers & RFC 7807 problem details
│   │   └── logging.py                # Structured JSON request logging & correlation IDs
│   │
│   ├── db/                           # Persistence Layer
│   │   ├── session.py                # Async SQLAlchemy / asyncpg connection pool engine
│   │   ├── base.py                   # Declarative Base
│   │   └── migrations/               # Alembic database migration scripts
│   │
│   ├── models/                       # SQLAlchemy ORM Models
│   │   ├── household.py              # Household & HouseholdMember models
│   │   ├── food.py                   # Global Food reference catalog
│   │   ├── inventory.py              # InventoryItem & StorageLocation models
│   │   ├── recipe.py                 # Recipe & RecipeIngredient models
│   │   └── shopping.py               # ShoppingListItem model
│   │
│   ├── schemas/                      # Pydantic v2 Validation & Serialization Schemas
│   │   ├── household.py              # HouseholdCreate, HouseholdMemberResponse
│   │   ├── inventory.py              # InventoryCreate, InventoryBatch, InventoryResponse
│   │   ├── recipe.py                 # RecipeSuggestionResponse, RecipeCookRequest
│   │   └── scan.py                   # ScanRequest, ScanReviewResponse
│   │
│   └── services/                     # Business Logic Services
│       ├── ai_client.py              # Async HTTPX client to AI microservice
│       ├── recipe_engine.py          # Ingredient matching & expiry weighting algorithm
│       ├── notification_service.py   # Expo push notification dispatcher
│       └── expiry_scheduler.py       # Daily morning cron for expiring items
│
├── tests/                            # Pytest Test Suite
│   ├── unit/                         # Schema, recipe engine, and service tests
│   ├── integration/                  # API endpoint tests with test database & mocked JWT
│   └── conftest.py                   # Fixtures & mock client providers
│
├── Dockerfile                        # Multi-stage hardened production Dockerfile
└── requirements.txt                  # Locked Python 3.11 dependencies
```

---

## 3. Database Isolation Strategy (Supabase RLS)
- All multi-tenant queries are guarded by a PostgreSQL `SECURITY DEFINER` helper function: `is_household_member(user_id, household_id)`.
- This eliminates infinite recursion in PostgreSQL policy checks while guaranteeing that no query can access or mutate inventory items outside the caller's household.
- Every API endpoint extracts the user's Supabase JWT, resolves their active household context via `X-Household-ID`, and validates membership before executing database queries.

---

## 4. API Endpoints Contract (Target Final State)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/health` | Service liveness & database readiness check | Public |
| `POST` | `/api/v1/households` | Create new household (creator becomes `owner`) | Bearer JWT |
| `POST` | `/api/v1/households/join` | Join household using 6-character alphanumeric code | Bearer JWT |
| `GET` | `/api/v1/households/me` | Get active household details and member list | Bearer JWT |
| `GET` | `/api/v1/inventory` | List active inventory with search & zone filters | Bearer JWT + Household |
| `POST` | `/api/v1/inventory/batch` | Bulk insert items confirmed from camera/OCR scan | Bearer JWT + Household |
| `PATCH` | `/api/v1/inventory/{id}` | Update quantity, storage zone, or expiry date | Bearer JWT + Household |
| `POST` | `/api/v1/inventory/{id}/consume` | Mark item as consumed and prompt shopping restock | Bearer JWT + Household |
| `POST` | `/api/v1/scan` | Relay image to AI microservice for OCR/vision parsing | Bearer JWT + Household |
| `GET` | `/api/v1/recipes/suggested` | Return recipes ranked by in-stock ingredients & expiry | Bearer JWT + Household |
| `POST` | `/api/v1/recipes/{id}/cook` | Deduct required recipe ingredients from active inventory | Bearer JWT + Household |
| `POST` | `/api/v1/notifications/token` | Register Expo Push Token for mobile device | Bearer JWT |
