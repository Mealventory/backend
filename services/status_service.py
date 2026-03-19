from datetime import date

def calculate_inventory_status(expiry_date_value) -> str:
    if not expiry_date_value:
        return "fresh"

    if isinstance(expiry_date_value, str):
        expiry = date.fromisoformat(expiry_date_value)
    elif isinstance(expiry_date_value, date):
        expiry = expiry_date_value
    else:
        return "fresh"

    today = date.today()
    days_left = (expiry - today).days

    if days_left < 0:
        return "expired"
    elif days_left <= 3:
        return "expiring_soon"
    else:
        return "fresh"