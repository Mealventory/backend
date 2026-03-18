from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.inventory import InventoryItem
from app.models.user import User
from app.schemas.inventory import InventoryItemCreate, InventoryItemOut
from app.services.expiry_service import calculate_expiry
from app.models.food import Food
from datetime import datetime, timezone

router = APIRouter()


@router.get("/", response_model=List[InventoryItemOut])
def list_inventory(
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	"""Return all inventory items belonging to the current user."""
	return (
		db.query(InventoryItem)
		.filter(InventoryItem.user_id == current_user.id)
		.all()
	)


@router.post("/", response_model=InventoryItemOut, status_code=status.HTTP_201_CREATED)
def add_inventory_item(
	item: InventoryItemCreate,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	"""Manually add a food item to the current user's inventory."""
	food = db.query(Food).filter(Food.id == item.food_id).first()
	if food is None:
		raise HTTPException(status_code=404, detail="Food not found")

	expiry = item.expiry_date
	if expiry is None and food.avg_shelf_life_days:
		expiry = calculate_expiry(datetime.now(timezone.utc), food.avg_shelf_life_days)

	db_item = InventoryItem(
		user_id=current_user.id,
		food_id=item.food_id,
		expiry_date=expiry,
	)
	db.add(db_item)
	db.commit()
	db.refresh(db_item)
	return db_item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(
	item_id: int,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	"""Remove an item from the current user's inventory."""
	db_item = (
		db.query(InventoryItem)
		.filter(InventoryItem.id == item_id, InventoryItem.user_id == current_user.id)
		.first()
	)
	if db_item is None:
		raise HTTPException(status_code=404, detail="Item not found")
	db.delete(db_item)
	db.commit()