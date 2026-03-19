from core.supabase_client import supabase
from datetime import date, timedelta
from services.status_service import calculate_inventory_status


def get_inventory(days_until_expiry: int | None = None):
    query = supabase.table("inventory").select(
        "*, food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)"
    )

    if days_until_expiry is not None:
        today = date.today()
        future_date = today + timedelta(days=days_until_expiry)

        query = (
            query
            .gte("expiry_date", today.isoformat())
            .lte("expiry_date", future_date.isoformat())
        )

    response = query.execute()
    return response.data

def get_inventory_item_by_id(item_id: int):
    response = (
        supabase.table("inventory")
        .select("*, food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)")
        .eq("id", item_id)
        .execute()
    )
    return response.data

def create_inventory_item(item_data: dict):
    item_data["status"] = calculate_inventory_status(item_data.get("expiry_date"))
    response = supabase.table("inventory").insert(item_data).execute()
    return response.data

def delete_inventory_item(item_id: int):
    response = supabase.table("inventory").delete().eq("id", item_id).execute()
    return response.data

def update_inventory_item(item_id: int, item_data: dict):
    if "expiry_date" in item_data:
        item_data["status"] = calculate_inventory_status(item_data.get("expiry_date"))

    response = supabase.table("inventory").update(item_data).eq("id", item_id).execute()
    return response.data