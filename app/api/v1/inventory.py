from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.inventory import InventoryItemCreate, InventoryItemOut
from app.services import inventory_service

router = APIRouter()


@router.get("/", response_model=List[InventoryItemOut])
def list_inventory(
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
    'Return all inventory items belonging to the current user.'
    return inventory_service.list_inventory(current_user, db)


@router.post("/", response_model=InventoryItemOut, status_code=status.HTTP_201_CREATED)
def add_inventory_item(
	item: InventoryItemCreate,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
    "Manually add a food item to the current user's inventory."
    return inventory_service.add_inventory_item(item, current_user, db)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(
	item_id: int,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
    "Remove an item from the current user's inventory."
    return inventory_service.delete_inventory_item(item_id, current_user, db)
