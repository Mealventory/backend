from fastapi import APIRouter, Depends
from core.supabase_client import supabase
from core.auth import get_current_user

router = APIRouter()

@router.get("/")
def health_check():
    try:
        supabase.table("food_items").select("id").limit(1).execute()
        return {"status": "ok", "database": "connected"}
    except Exception:
        return {"status": "error", "database": "disconnected"}
    
@router.get("/protected")
def protected_health_check(current_user=Depends(get_current_user)):
    return {
        "status": "ok",
        "authenticated": True,
        "user_id": current_user.id,
        "email": current_user.email,
    }