from core.supabase_client import supabase
from datetime import date, timedelta
from services.status_service import calculate_inventory_status

def user_exists(user_id: int) -> bool:
    response = supabase.table("users").select("id").eq("id", user_id).execute()
    return len(response.data) > 0

def food_item_exists(food_item_id: int) -> bool:
    response = supabase.table("food_items").select("id").eq("id", food_item_id).execute()
    return len(response.data) > 0

def get_inventory(
    auth_user_id: str | None = None,
    days_until_expiry: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
):
    query = supabase.table("inventory").select(
        "*, food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)"
    )

    if auth_user_id is not None:
        query = query.eq("auth_user_id", auth_user_id)

    # Filter by expiry window
    if days_until_expiry is not None:
        today = date.today()
        future_date = today + timedelta(days=days_until_expiry)

        query = (
            query
            .gte("expiry_date", today.isoformat())
            .lte("expiry_date", future_date.isoformat())
        )

    # Sorting
    allowed_sort_fields = {"id", "purchase_date", "expiry_date", "created_at", "quantity", "status"}

    if sort_by in allowed_sort_fields:
        ascending = sort_order.lower() == "asc"
        query = query.order(sort_by, desc=not ascending)

    # Pagination (we’ll wire this properly next step, but safe to include now)
    if limit is not None:
        if offset is None:
            offset = 0
        query = query.range(offset, offset + limit - 1)

    response = query.execute()
    return response.data

def get_inventory_item_by_id(item_id: int, auth_user_id: str | None = None):
    query = (
        supabase.table("inventory")
        .select("*, food_items(id, name, category, default_unit, barcode, typical_shelf_life_days)")
        .eq("id", item_id)
    )

    if auth_user_id is not None:
        query = query.eq("auth_user_id", auth_user_id)

    response = query.execute()
    return response.data

def create_inventory_item(item_data: dict):
    item_data["status"] = calculate_inventory_status(item_data.get("expiry_date"))
    response = supabase.table("inventory").insert(item_data).execute()
    return response.data

def delete_inventory_item(item_id: int, auth_user_id: str | None = None):
    query = supabase.table("inventory").delete().eq("id", item_id)

    if auth_user_id is not None:
        query = query.eq("auth_user_id", auth_user_id)

    response = query.execute()
    return response.data

def update_inventory_item(item_id: int, item_data: dict, auth_user_id: str | None = None):
    if "expiry_date" in item_data:
        item_data["status"] = calculate_inventory_status(item_data.get("expiry_date"))

    query = supabase.table("inventory").update(item_data).eq("id", item_id)

    if auth_user_id is not None:
        query = query.eq("auth_user_id", auth_user_id)

    response = query.execute()
    return response.data