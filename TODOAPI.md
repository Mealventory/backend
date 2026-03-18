# TODO API

This file tracks the immediate next steps for the FastAPI layer in the backend repo.

## Goal
Deliver a stable, documented, testable API contract for frontend and ai-services integration.

## 1. Route Contract Stabilization
- [ ] Freeze route base path as `/api/v1`.
- [ ] Confirm and document current endpoints:
  - [ ] `GET /` health check
  - [ ] `POST /api/v1/users/register`
  - [ ] `GET /api/v1/users/me`
  - [ ] `GET /api/v1/inventory/`
  - [ ] `POST /api/v1/inventory/`
  - [ ] `DELETE /api/v1/inventory/{item_id}`
  - [ ] `POST /api/v1/scan/`
  - [ ] `GET /api/v1/recipes/`
- [ ] Add explicit response models for scan and recipes payloads (avoid loose dict responses).

## 2. Request/Response Validation
- [ ] Add strict Pydantic schemas for every request and response body.
- [ ] Ensure optional fields have explicit defaults.
- [ ] Add typed error responses (`401`, `404`, `422`, `500`) to route decorators.

## 3. API Documentation
- [ ] Complete endpoint docstrings (purpose, auth requirement, expected payload).
- [ ] Add examples to request models for Swagger clarity.
- [ ] Verify docs render correctly at `/docs` and `/redoc`.

## 4. Auth Integration Quality
- [ ] Confirm Firebase token verification behavior for expired/invalid tokens.
- [ ] Add one protected endpoint smoke test with a mocked token.
- [ ] Add one unauthorized access test per protected route.

## 5. Frontend Integration Readiness
- [ ] Add a short API contract table in README (method, path, auth, response).
- [ ] Define stable error format for frontend handling.
- [ ] Add pagination strategy for inventory list endpoint if needed.

## 6. Testing
- [ ] Add pytest setup and TestClient configuration.
- [ ] Add tests for:
  - [ ] users registration/me
  - [ ] inventory CRUD
  - [ ] scan failure/success flows
  - [ ] recipes with and without inventory items
- [ ] Enforce minimum API test coverage target (at least 70%).

## Done Criteria
- All API endpoints have stable schemas and tests.
- Swagger is accurate and complete.
- Frontend can integrate without guessing payload shapes.
