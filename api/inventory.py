from typing import List
from fastapi import APIRouter, Query, HTTPException, Depends
from services.inventory_service import (
    get_inventory,
    create_inventory_item,
    delete_inventory_item,
    update_inventory_item,
    get_inventory_item_by_id,
    food_item_exists,
)
from schemas.inventory_schema import InventoryCreate, InventoryUpdate, InventoryResponse
from core.auth import get_current_user


router = APIRouter()

@router.get("/", response_model=List[InventoryResponse])
def read_inventory(
    days_until_expiry: int | None = Query(default=None),
    limit: int | None = Query(default=None),
    offset: int | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc"),
    current_user=Depends(get_current_user),
):
    return get_inventory(
        auth_user_id=current_user.id,
        days_until_expiry=days_until_expiry,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

@router.get("/{item_id}", response_model=InventoryResponse)
def read_inventory_item(item_id: int, current_user=Depends(get_current_user)):
    item = get_inventory_item_by_id(item_id, auth_user_id=current_user.id)

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return item[0]

@router.post("/", response_model=List[InventoryResponse])
def add_inventory(item: InventoryCreate, current_user=Depends(get_current_user)):
    if not food_item_exists(item.food_item_id):
        raise HTTPException(status_code=404, detail="Food item not found")

    item_data = item.model_dump(mode="json")
    item_data["auth_user_id"] = current_user.id
    item_data["user_id"] = 1

    return create_inventory_item(item_data)

@router.delete("/{item_id}", response_model=List[InventoryResponse])
def delete_inventory(item_id: int, current_user=Depends(get_current_user)):
    deleted_item = delete_inventory_item(item_id, auth_user_id=current_user.id)

    if not deleted_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return deleted_item

@router.patch("/{item_id}", response_model=List[InventoryResponse])
def update_inventory(item_id: int, item: InventoryUpdate, current_user=Depends(get_current_user)):
    update_data = item.model_dump(mode="json", exclude_unset=True)

    if "user_id" in update_data:
        del update_data["user_id"]

    if "food_item_id" in update_data and not food_item_exists(update_data["food_item_id"]):
        raise HTTPException(status_code=404, detail="Food item not found")

    updated_item = update_inventory_item(item_id, update_data, auth_user_id=current_user.id)

    if not updated_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return updated_item