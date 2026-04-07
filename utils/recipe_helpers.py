from datetime import date


def split_inventory_for_recipe_generation(items):
    today = date.today()
    priority_items = []
    other_items = []

    for item in items:
        expiry_date = item.get("expiry_date")
        name = item.get("food_items", {}).get("name") or item.get("name")
        quantity = item.get("quantity")
        unit = item.get("unit")
        storage_location = item.get("storage_location")

        formatted_item = {
            "name": name,
            "quantity": quantity,
            "unit": unit,
            "storage_location": storage_location,
            "expiry_date": expiry_date,
        }

        if expiry_date:
            days_left = (date.fromisoformat(expiry_date) - today).days
            if days_left <= 3:
                priority_items.append(formatted_item)
            else:
                other_items.append(formatted_item)
        else:
            other_items.append(formatted_item)

    priority_items.sort(key=lambda x: x["expiry_date"] or "9999-12-31")
    return priority_items, other_items