from core.supabase_client import supabase
from datetime import date, timedelta

def get_inventory(days_until_expiry: int | None = None):
    query = supabase.table("inventory").select("*")

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
    response = supabase.table("inventory").select("*").eq("id", item_id).execute()
    return response.data

def create_inventory_item(item_data: dict):
    response = supabase.table("inventory").insert(item_data).execute()
    return response.data

def delete_inventory_item(item_id: int):
    response = supabase.table("inventory").delete().eq("id", item_id).execute()
    return response.data

def update_inventory_item(item_id: int, item_data: dict):
    response = supabase.table("inventory").update(item_data).eq("id", item_id).execute()
    return response.data
