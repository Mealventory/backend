import httpx
from app.core.config import settings
from app.services.recipe_ai_service import generate_recipe_suggestions


async def get_recipes_for_inventory(food_names: list[str]) -> dict:
	"""Call the ai-service or fallback to OpenRouter recipe generator."""
	try:
		async with httpx.AsyncClient() as client:
			response = await client.post(
				f"{settings.AI_SERVICE_URL}/recipes",
				json={"items": food_names},
				timeout=5.0,
			)
			if response.status_code == 200:
				return response.json()
	except Exception:
		pass

	# Fallback to backend's OpenRouter recipe AI generator
	priority_items = [{"name": name, "days_until_expiry": 2} for name in food_names[:2]]
	other_items = [{"name": name} for name in food_names[2:]]
	return await generate_recipe_suggestions(priority_items, other_items)


from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.inventory import InventoryItem
from app.models.food import Food
from app.models.user import User

async def get_inventory_recipes(current_user: User, db: Session):
    "\n\tReturn recipe suggestions from the ai-service based on the user's\n\tcurrent inventory.\n\t"
    items = db.query(InventoryItem).filter(InventoryItem.user_id == current_user.id).all()
    if not items:
        raise HTTPException(status_code=404, detail='No items in inventory')
    food_names = []
    for item in items:
        food = db.query(Food).filter(Food.id == item.food_id).first()
        if food:
            food_names.append(food.name)
    return await get_recipes_for_inventory(food_names)
