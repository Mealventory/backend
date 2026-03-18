# TODO BACKEND

This file tracks backend-level work beyond route handlers, including database, operational readiness, and maintainability.

## Goal
Make the backend robust, reproducible, and ready for real data and deployment workflows.

## 1. Database Connection and Lifecycle
- [ ] Finalize `.env` with real `DATABASE_URL` and verify app startup against running PostgreSQL.
- [ ] Add connectivity check endpoint or startup log for DB availability.
- [ ] Decide and document local DB strategy (Docker PostgreSQL vs installed PostgreSQL).

## 2. Migrations (Critical)
- [ ] Initialize and configure Alembic migration environment.
- [ ] Create initial migration for `users`, `foods`, and `inventory_items`.
- [ ] Apply migration on clean database successfully.
- [ ] Add migration command section to setup docs.

## 3. Seed Data and Domain Setup
- [ ] Create seed script for base food catalog (`foods` table).
- [ ] Define category/subtype and average shelf life source of truth.
- [ ] Ensure scan flow gracefully handles unknown food names.

## 4. Service Reliability
- [ ] Add timeout + retry strategy for ai-service HTTP calls.
- [ ] Add centralized error mapping when ai-service is unavailable.
- [ ] Add structured logging for route/service failures.

## 5. Security and Configuration
- [ ] Replace permissive CORS wildcard before production.
- [ ] Verify Firebase credentials loading strategy for local/dev/prod.
- [ ] Add `.env.example` fields for all required runtime configs.

## 6. Code Quality and Standards
- [ ] Normalize indentation/style across all modules.
- [ ] Add linting and formatting (ruff/black or equivalent).
- [ ] Add pre-commit checks for lint + tests.

## 7. CI/CD Foundation
- [ ] Add GitHub Actions workflow for:
  - [ ] dependency install
  - [ ] lint
  - [ ] tests
- [ ] Optionally add container build check.

## Done Criteria
- Backend can be cloned, configured, migrated, seeded, and started with documented steps.
- Database schema lifecycle is controlled via migrations.
- ai-service failures are handled predictably.
