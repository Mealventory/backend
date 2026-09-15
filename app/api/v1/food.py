from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date

from app.dependencies.database import get_db
from app.services import food_service

router = APIRouter()


@router.post("/predict-expiry/{food_id}")
async def predict_food_expiry(
    food_id: int,
    purchase_date: date,
    temperature: float,
    humidity: float,
    db: Session = Depends(get_db)
):
    """Predict the expiry date for a food item using storage conditions."""
    return food_service.predict_food_expiry(food_id, purchase_date, temperature, humidity, db)
