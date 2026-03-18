# TODO AI SERVICE INTEGRATION

This file tracks what must be completed before connecting backend to the ai-services repo in production-like flows.

## Goal
Define and verify a strict integration contract between backend and ai-services so both repos evolve safely.

## 1. Contract Definition (Must Do First)
- [ ] Freeze endpoint contracts expected by backend:
  - [ ] `POST /detect-food`
  - [ ] `POST /recipes`
- [ ] Document exact request payload shapes and required fields.
- [ ] Document exact response payload shapes and required fields.
- [ ] Define common error payload format (`4xx`, `5xx`) for both services.

## 2. Schema Alignment
- [ ] Add Pydantic models in backend for ai-service responses.
- [ ] Validate ai-service responses against those schemas.
- [ ] Fail gracefully with useful error when response is invalid.

## 3. Environment and Networking
- [ ] Define `AI_SERVICE_URL` per environment (local/dev/staging/prod).
- [ ] Confirm backend can reach ai-service over expected network path.
- [ ] Decide timeout, retry count, and circuit-breaker policy.

## 4. Functional Integration Tests
- [ ] Create integration tests using mocked ai-service responses.
- [ ] Add at least one real end-to-end test against a running ai-service instance:
  - [ ] scan image -> detected items -> inventory insert
  - [ ] inventory -> recipe suggestions
- [ ] Test ai-service downtime behavior and fallback response.

## 5. Data Semantics Agreement
- [ ] Define canonical food naming strategy (`apple` vs `red apple`, singular/plural).
- [ ] Define confidence thresholds for detections.
- [ ] Decide behavior for low-confidence or unknown detections.

## 6. Operational Readiness
- [ ] Add request correlation ID tracing across backend and ai-service logs.
- [ ] Add latency/error metrics for ai-service calls.
- [ ] Define rollback/feature-flag strategy if ai-service response contract changes.

## 7. Cross-Repo Process
- [ ] Create a shared versioned contract document in docs repo.
- [ ] Require contract update PR before breaking ai-service response changes.
- [ ] Assign owners/reviewers from both backend and ai-services for contract changes.

## Done Criteria
- Backend and ai-services share a documented, versioned API contract.
- Integration tests pass for success and failure scenarios.
- Connecting both repos does not require manual payload guesswork.
