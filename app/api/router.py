from fastapi import APIRouter
from app.core.auth_errors import AUTH_RESPONSES
from app.api.v1 import inventory, scan, recipes, users
from app.api.v1 import food


api_router = APIRouter(prefix="/api/v1", responses=AUTH_RESPONSES)


api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
api_router.include_router(scan.router, prefix="/scan", tags=["Scan"])
api_router.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
api_router.include_router(food.router, prefix="/food", tags=["Food"])