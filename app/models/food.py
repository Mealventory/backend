# models/food.py

from datetime import timedelta
from app.models.food import Food
from sqlalchemy.orm import Session

# Modify the calculate_expiry_date to factor in temperature and humidity (optional)
def calculate_expiry_date(purchase_date, avg_shelf_life_days, temperature=None, humidity=None):
    """
    Calculate the expiry date based on purchase date and shelf life.
    Optionally, adjust based on temperature and humidity.
    """

    if not purchase_date or not avg_shelf_life_days:
        return None

    # Adjust shelf life based on temperature and humidity if needed
    # For simplicity, here we use placeholders for how temperature and humidity might affect shelf life
    if temperature:
        # Example: high temperature reduces shelf life by 10% (this is just an example logic)
        avg_shelf_life_days *= (1 - 0.1 * (temperature - 20) / 10)

    if humidity:
        # Example: higher humidity could reduce shelf life by 5%
        avg_shelf_life_days *= (1 - 0.05 * (humidity - 50) / 10)

    expiry_date = purchase_date + timedelta(days=avg_shelf_life_days)
    return expiry_date

def update_expiry_date(food_id: int, purchase_date: str, db: Session):
    """
    Update the expiry date for a food item based on purchase date and additional factors like temperature and humidity.
    """
    # Get the food item from the database
    food = db.query(Food).filter(Food.id == food_id).first()

    if food:
        # Get the temperature and humidity from the food item (if available)
        temperature = food.temperature  # Assuming food object has these attributes
        humidity = food.humidity

        # Calculate the new expiry date using the updated function
        expiry_date = calculate_expiry_date(purchase_date, food.avg_shelf_life_days, temperature, humidity)

        if expiry_date:
            food.expiry_date = expiry_date

            # Commit the changes to the database
            db.commit()
            db.refresh(food)
            return food

    return None