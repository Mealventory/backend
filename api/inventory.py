from fastapi import APIRouter
from schemas.inventory_schema import InventoryCreate
from services.inventory_service import (
    get_inventory,
    create_inventory_item,
    delete_inventory_item,
    update_inventory_item,
    get_inventory_item_by_id
)

from schemas.inventory_schema import InventoryCreate, InventoryUpdate

router = APIRouter()

@router.get("/")
def read_inventory():
    return get_inventory()

@router.post("/")
def add_inventory(item: InventoryCreate):
    return create_inventory_item(item.model_dump())

@router.delete("/{item_id}")
def delete_inventory(item_id: int):
    return delete_inventory_item(item_id)

@router.patch("/{item_id}")
def update_inventory(item_id: int, item: InventoryUpdate):
    update_data = item.model_dump(exclude_unset=True)
    return update_inventory_item(item_id, update_data)

@router.get("/{item_id}")
def read_inventory_item(item_id: int):
    return get_inventory_item_by_id(item_id)