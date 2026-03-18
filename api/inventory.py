from fastapi import APIRouter
from schemas.inventory_schema import InventoryCreate
from services.inventory_service import get_inventory, create_inventory_item

router = APIRouter()

@router.get("/")
def read_inventory():
    return get_inventory()

@router.post("/")
def add_inventory(item: InventoryCreate):
    return create_inventory_item(item.model_dump())