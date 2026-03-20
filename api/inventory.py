from typing import List
from fastapi import APIRouter, Query, HTTPException
from services.inventory_service import (
    get_inventory,
    create_inventory_item,
    delete_inventory_item,
    update_inventory_item,
    get_inventory_item_by_id,
    user_exists,
    food_item_exists,
)
from schemas.inventory_schema import InventoryCreate, InventoryUpdate, InventoryResponse

router = APIRouter()

@router.get("/", response_model=List[InventoryResponse])
def read_inventory(
    days_until_expiry: int | None = Query(default=None),
    limit: int | None = Query(default=None),
    offset: int | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc"),
):
    return get_inventory(
        days_until_expiry=days_until_expiry,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

@router.get("/{item_id}", response_model=InventoryResponse)
def read_inventory_item(item_id: int):
    item = get_inventory_item_by_id(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return item[0]

@router.post("/", response_model=List[InventoryResponse])
def add_inventory(item: InventoryCreate):
    if not user_exists(item.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    if not food_item_exists(item.food_item_id):
        raise HTTPException(status_code=404, detail="Food item not found")

    return create_inventory_item(item.model_dump(mode="json"))

@router.delete("/{item_id}", response_model=List[InventoryResponse])
def delete_inventory(item_id: int):
    deleted_item = delete_inventory_item(item_id)

    if not deleted_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return deleted_item

@router.patch("/{item_id}", response_model=List[InventoryResponse])
def update_inventory(item_id: int, item: InventoryUpdate):
    update_data = item.model_dump(mode="json", exclude_unset=True)

    if "user_id" in update_data and not user_exists(update_data["user_id"]):
        raise HTTPException(status_code=404, detail="User not found")

    if "food_item_id" in update_data and not food_item_exists(update_data["food_item_id"]):
        raise HTTPException(status_code=404, detail="Food item not found")

    updated_item = update_inventory_item(item_id, update_data)

    if not updated_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return updated_item