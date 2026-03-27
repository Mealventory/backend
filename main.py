from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import api.test as test
import api.inventory as inventory
from api.food_items import router as food_items_router
from api.health import router as health_router
from api.recipes import router as recipes_router
from api.recipe_ingredients import router as recipe_ingredients_router
from core.logging_middleware import log_requests
from fastapi.security import HTTPBearer

app = FastAPI()

security = HTTPBearer()

@app.get("/")
def home():
    return {"message": "Mealventory backend is running"}

# app.include_router(test.router)
app.include_router(inventory.router, prefix="/inventory")
app.include_router(food_items_router, prefix="/food-items", tags=["Food Items"])
app.include_router(health_router, prefix="/health", tags=["Health"])
app.include_router(recipes_router, prefix="/recipes", tags=["Recipes"])
app.include_router(recipe_ingredients_router, prefix="/recipes", tags=["Recipe Ingredients"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"ERROR: {request.method} {request.url.path} - {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

app.middleware("http")(log_requests)