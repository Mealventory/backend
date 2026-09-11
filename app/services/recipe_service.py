import httpx
from app.core.config import settings
from services.recipe_ai_service import generate_recipe_suggestions


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
