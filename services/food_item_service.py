from core.supabase_client import supabase

def get_food_items():
    response = supabase.table("food_items").select("*").execute()
    return response.data

def get_food_item_by_id(item_id: int):
    response = supabase.table("food_items").select("*").eq("id", item_id).execute()
    return response.data

def create_food_item(item_data: dict):
    response = supabase.table("food_items").insert(item_data).execute()
    return response.data

def update_food_item(item_id: int, item_data: dict):
    response = supabase.table("food_items").update(item_data).eq("id", item_id).execute()
    return response.data

def delete_food_item(item_id: int):
    response = supabase.table("food_items").delete().eq("id", item_id).execute()
    return response.data