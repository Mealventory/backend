import httpx
from app.core.config import settings


async def get_recipes_for_inventory(food_names: list[str]) -> dict:
	"""Call the ai-service to get recipe suggestions for the given food items."""
	async with httpx.AsyncClient() as client:
		response = await client.post(
			f"{settings.AI_SERVICE_URL}/recipes",
			json={"items": food_names},
			timeout=30.0,
		)
	response.raise_for_status()
	return response.json()
