from fastapi import APIRouter

from app.api.v1 import activity, food, health, households, items, recipes, scan, shopping, stores, users
from app.core.auth_errors import PROBLEM_RESPONSES


api_router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSES)


api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(scan.router, prefix="/scan", tags=["Scan"])
api_router.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
api_router.include_router(food.router, prefix="/food", tags=["Food"])
api_router.include_router(households.router, prefix="/households", tags=["Households"])
api_router.include_router(items.router, prefix="/items", tags=["Household inventory"])

api_router.include_router(shopping.router, prefix="/shopping", tags=["Shopping list"])
api_router.include_router(activity.router, prefix="/activity", tags=["Household activity"])
api_router.include_router(stores.router, prefix="/stores", tags=["Household stores"])

api_router.include_router(health.router, prefix="/health", tags=["Health"])

from app.api.v1 import notifications

api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
