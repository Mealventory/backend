# models/food.py

from datetime import timedelta
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import Session
from app.db.base import Base


class Food(Base):

    __tablename__ = "foods"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    type = Column(String)
    subtype = Column(String)
    avg_shelf_life_days = Column(Integer)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)


def calculate_expiry_date(purchase_date, avg_shelf_life_days, temperature=None, humidity=None):
    """
    Calculate the expiry date based on purchase date and shelf life.
    Optionally, adjust based on temperature and humidity.
    """
    if not purchase_date or not avg_shelf_life_days:
        return None

    shelf_life = float(avg_shelf_life_days)

    if temperature is not None:
        shelf_life *= (1 - 0.1 * (temperature - 20) / 10)

    if humidity is not None:
        shelf_life *= (1 - 0.05 * (humidity - 50) / 10)

    expiry_date = purchase_date + timedelta(days=shelf_life)
    return expiry_date


def update_expiry_date(food_id: int, purchase_date: str, db: Session):
    """
    Update the expiry date for a food item based on purchase date and additional factors.
    """
    food = db.query(Food).filter(Food.id == food_id).first()

    if food:
        temperature = getattr(food, "temperature", None)
        humidity = getattr(food, "humidity", None)

        expiry_date = calculate_expiry_date(purchase_date, food.avg_shelf_life_days, temperature, humidity)

        if expiry_date:
            food.expiry_date = expiry_date
            db.commit()
            db.refresh(food)
            return food

    return None