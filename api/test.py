from fastapi import APIRouter
from core.supabase_client import supabase

router = APIRouter()

@router.get("/test-db")
def test_db():
    response = supabase.table("food_items").select("*").execute()
    return response.data