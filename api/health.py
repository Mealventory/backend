from fastapi import APIRouter
from core.supabase_client import supabase

router = APIRouter()

@router.get("/")
def health_check():
    try:
        supabase.table("food_items").select("id").limit(1).execute()
        return {"status": "ok", "database": "connected"}
    except Exception:
        return {"status": "error", "database": "disconnected"}