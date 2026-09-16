from datetime import date
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.food import Food
from app.services.expiry_service import predict_expiry_date


def predict_food_expiry(food_id: int, purchase_date: date, temperature: float,
                        humidity: float, db: Session):
    '\n    Predict and update the expiry date for a food item based on purchase date\n    and environmental conditions (temperature and humidity).\n    '
    food_item = db.query(Food).filter(Food.id == food_id).first()
    if not food_item:
        raise HTTPException(status_code=404, detail='Food item not found')
    food_item.purchase_date = purchase_date
    predicted_expiry = predict_expiry_date(food_item, temperature, humidity)
    food_item.expiry_date = predicted_expiry
    db.commit()
    db.refresh(food_item)
    return {'message': 'Expiry date predicted successfully', 'food_id': food_item.id, 'name': food_item.name, 'purchase_date': food_item.purchase_date, 'predicted_expiry_date': food_item.expiry_date}
