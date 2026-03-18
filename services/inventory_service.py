from core.supabase_client import supabase

def get_inventory():
    response = supabase.table("inventory").select("*").execute()
    return response.data

def create_inventory_item(item_data: dict):
    response = supabase.table("inventory").insert(item_data).execute()
    return response.data