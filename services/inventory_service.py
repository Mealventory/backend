from core.supabase_client import supabase

def get_inventory():
    response = supabase.table("inventory").select("*").execute()
    return response.data