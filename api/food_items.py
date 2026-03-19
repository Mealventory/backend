from fastapi import APIRouter, HTTPException
from schemas.food_item_schema import FoodItemCreate, FoodItemUpdate
from services.food_item_service import (
    get_food_items,
    get_food_item_by_id,
    create_food_item,
    update_food_item,
    delete_food_item,
)

router = APIRouter()

@router.get("/")
def read_food_items():
    return get_food_items()

@router.get("/{item_id}")
def read_food_item(item_id: int):
    item = get_food_item_by_id(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Food item not found")

    return item

@router.post("/")
def add_food_item(item: FoodItemCreate):
    return create_food_item(item.model_dump())

@router.patch("/{item_id}")
def update_food_item_route(item_id: int, item: FoodItemUpdate):
    update_data = item.model_dump(exclude_unset=True)
    updated_item = update_food_item(item_id, update_data)

    if not updated_item:
        raise HTTPException(status_code=404, detail="Food item not found")

    return updated_item

@router.delete("/{item_id}")
def delete_food_item_route(item_id: int):
    deleted_item = delete_food_item(item_id)

    if not deleted_item:
        raise HTTPException(status_code=404, detail="Food item not found")

    return deleted_item