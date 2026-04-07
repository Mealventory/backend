from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.db.session import get_db
from app.models.food import Food
from app.services.expiry_service import predict_expiry_date

router = APIRouter()


@router.post("/predict-expiry/{food_id}")
async def predict_food_expiry(
    food_id: int,
    purchase_date: date,
    temperature: float,
    humidity: float,
    db: Session = Depends(get_db)
):
    """
    Predict and update the expiry date for a food item based on purchase date
    and environmental conditions (temperature and humidity).
    """
    # Fetch the food item from the database
    food_item = db.query(Food).filter(Food.id == food_id).first()
    if not food_item:
        raise HTTPException(status_code=404, detail="Food item not found")

    # Update the purchase date
    food_item.purchase_date = purchase_date

    # Predict the expiry date using the ML model
    predicted_expiry = predict_expiry_date(food_item, temperature, humidity)
    food_item.expiry_date = predicted_expiry

    # Commit the changes to the database
    db.commit()
    db.refresh(food_item)

    return {
        "message": "Expiry date predicted successfully",
        "food_id": food_item.id,
        "name": food_item.name,
        "purchase_date": food_item.purchase_date,
        "predicted_expiry_date": food_item.expiry_date
    }