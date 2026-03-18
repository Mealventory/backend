from core.supabase_client import supabase

def get_inventory():
    response = supabase.table("inventory").select("*").execute()
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