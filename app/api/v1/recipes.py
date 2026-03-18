from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.inventory import InventoryItem
from app.models.food import Food
from app.models.user import User
from app.services.recipe_service import get_recipes_for_inventory

router = APIRouter()


@router.get("/")
async def get_recipes(
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	"""
	Return recipe suggestions from the ai-service based on the user's
	current inventory.
	"""
	items = (
		db.query(InventoryItem)
		.filter(InventoryItem.user_id == current_user.id)
		.all()
	)
	if not items:
		raise HTTPException(status_code=404, detail="No items in inventory")

	food_names = []
	for item in items:
		food = db.query(Food).filter(Food.id == item.food_id).first()
		if food:
			food_names.append(food.name)

	return await get_recipes_for_inventory(food_names)