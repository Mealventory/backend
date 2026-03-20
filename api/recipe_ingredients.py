from fastapi import APIRouter, HTTPException
from schemas.recipe_ingredient_schema import RecipeIngredientCreate
from services.recipe_ingredient_service import (
    add_recipe_ingredient,
    delete_recipe_ingredient,
)
from services.recipe_service import get_recipe_by_id
from services.inventory_service import food_item_exists

router = APIRouter()

@router.post("/{recipe_id}/ingredients")
def add_recipe_ingredient_route(recipe_id: int, ingredient: RecipeIngredientCreate):
    recipe = get_recipe_by_id(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if not food_item_exists(ingredient.food_item_id):
        raise HTTPException(status_code=404, detail="Food item not found")

    return add_recipe_ingredient(recipe_id, ingredient.model_dump(mode="json"))

@router.delete("/{recipe_id}/ingredients/{food_item_id}")
def delete_recipe_ingredient_route(recipe_id: int, food_item_id: int):
    recipe = get_recipe_by_id(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    deleted = delete_recipe_ingredient(recipe_id, food_item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")

    return deleted