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
backend/
│
├── app/
│   │
│   ├── main.py
│   │
│   ├── api/
│   │   ├── router.py
│   │   └── v1/
│   │       ├── inventory.py
│   │       ├── auth.py
│   │       ├── scan.py
│   │       └── recipes.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── security.py
│   │
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   └── migrations/
│   │
│   ├── models/
│   │   └── inventory.py
│   │
│   ├── schemas/
│   │   └── inventory.py
│   │
│   ├── services/
│   │   ├── vision_service.py
│   │   ├── recipe_service.py
│   │   └── expiry_service.py
│   │
│   └── dependencies/
│       └── auth.py
│
├── tests/
│
├── requirements.txt
├── .env.example
└── README.md