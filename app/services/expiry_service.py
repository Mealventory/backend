from datetime import timedelta

def calculate_expiry(date_added, shelf_life_days):
    return date_added + timedelta(days=shelf_life_days)