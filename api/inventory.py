from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def read_inventory():
    return {"message": "inventory route works"}