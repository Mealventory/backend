from fastapi import FastAPI
import api.test as test
import api.inventory as inventory

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Mealventory backend is running"}

# app.include_router(test.router)
app.include_router(inventory.router, prefix="/inventory")