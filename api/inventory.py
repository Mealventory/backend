from fastapi import APIRouter, Query, HTTPException
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
def read_inventory(days_until_expiry: int | None = Query(default=None)):
    return get_inventory(days_until_expiry)

@router.get("/{item_id}")
def read_inventory_item(item_id: int):
    item = get_inventory_item_by_id(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return item

@router.post("/")
def add_inventory(item: InventoryCreate):
    return create_inventory_item(item.model_dump())

@router.delete("/{item_id}")
def delete_inventory(item_id: int):
    deleted_item = delete_inventory_item(item_id)

    if not deleted_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return deleted_item

@router.patch("/{item_id}")
def update_inventory(item_id: int, item: InventoryUpdate):
    update_data = item.model_dump(exclude_unset=True)
    updated_item = update_inventory_item(item_id, update_data)

    if not updated_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return updated_item

