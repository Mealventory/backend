# Mealventory Backend

Core business logic service for Mealventory.

Responsible for inventory management, expiry engine, recipe filtering, and database operations.

Public API layer for the Mealventory ecosystem.

Handles request validation, routing, authentication verification, and orchestration between backend services.


---

## 🏗 Responsibilities

- Inventory CRUD operations
- Expiry prediction engine
- Recipe prioritization logic
- User profile management
- PostgreSQL database interaction
- Sends the data to ai-service

---

## 🛠 Tech Stack

- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic (migrations)
- Docker (to see)
- Firebase Admin SDK
- HTTPX (service-to-service calls)

---

## 🏗 Architecture Role

This service acts as:

- API Gateway
- Authentication verifier
- Request validator
- Service orchestrator

It communicates with:

- mealventory-ai-service

---

## 📂 Structure
