from fastapi import APIRouter, Depends, HTTPException
from core.auth import get_current_user
from services.recipe_ai_service import generate_recipe_suggestions
from utils.recipe_helpers import split_inventory_for_recipe_generation
from services.inventory_service import get_inventory
from schemas.recipe_ai import GeneratedRecipeResponse

router = APIRouter(prefix="/recipes", tags=["AI Recipes"])


@router.post("/generate", response_model=GeneratedRecipeResponse)
async def generate_recipes(current_user=Depends(get_current_user)):
    inventory_items = get_inventory(auth_user_id=current_user.id)

    if not inventory_items:
        raise HTTPException(status_code=404, detail="No inventory items found")

    priority_items, other_items = split_inventory_for_recipe_generation(inventory_items)

    if not priority_items and not other_items:
        raise HTTPException(status_code=404, detail="No usable inventory items found")

    recipes = await generate_recipe_suggestions(priority_items, other_items)
    return recipes