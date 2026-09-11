from datetime import timedelta, date, datetime


def calculate_expiry(date_added, shelf_life_days):
    """Calculate expiry date given date added and shelf life in days."""
    if not shelf_life_days:
        return None
    return date_added + timedelta(days=shelf_life_days)


def predict_expiry_date(food_item, temperature=None, humidity=None):
    """
    Predict expiry date for a food item considering storage conditions.
    """
    purchase_date = getattr(food_item, "purchase_date", None)
    if isinstance(purchase_date, str):
        purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()
    elif isinstance(purchase_date, datetime):
        purchase_date = purchase_date.date()
    elif not purchase_date:
        purchase_date = date.today()

    avg_shelf_life = getattr(food_item, "avg_shelf_life_days", 7) or 7
    shelf_life = float(avg_shelf_life)

    if temperature is not None:
        shelf_life *= (1 - 0.1 * (temperature - 20) / 10)

    if humidity is not None:
        shelf_life *= (1 - 0.05 * (humidity - 50) / 10)

    return purchase_date + timedelta(days=max(1.0, shelf_life))