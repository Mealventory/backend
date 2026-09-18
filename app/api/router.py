from fastapi import APIRouter
from app.core.auth_errors import AUTH_RESPONSES
from app.api.v1 import inventory, scan, recipes, users, households
from app.api.v1 import food, health
from app.api.v1 import items, shopping


api_router = APIRouter(prefix="/api/v1", responses=AUTH_RESPONSES)


api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
api_router.include_router(scan.router, prefix="/scan", tags=["Scan"])
api_router.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
api_router.include_router(food.router, prefix="/food", tags=["Food"])
api_router.include_router(households.router, prefix="/households", tags=["Households"])
api_router.include_router(items.router, prefix="/items", tags=["Household inventory"])

api_router.include_router(shopping.router, prefix="/shopping", tags=["Shopping list"])

api_router.include_router(health.router, prefix="/health", tags=["Health"])
