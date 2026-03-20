from fastapi import FastAPI
import api.test as test
import api.inventory as inventory
from api.food_items import router as food_items_router
from api.health import router as health_router
from api.recipes import router as recipes_router

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Mealventory backend is running"}

# app.include_router(test.router)
app.include_router(inventory.router, prefix="/inventory")
app.include_router(food_items_router, prefix="/food-items", tags=["Food Items"])
app.include_router(health_router, prefix="/health", tags=["Health"])
app.include_router(recipes_router, prefix="/recipes", tags=["Recipes"])