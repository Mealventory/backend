from typing import List
from fastapi import APIRouter, HTTPException
from schemas.recipe_schema import RecipeCreate, RecipeUpdate, RecipeResponse
from services.recipe_service import (
    get_recipes,
    get_recipe_by_id,
    create_recipe,
    update_recipe,
    delete_recipe,
)

router = APIRouter()

@router.get("/", response_model=List[RecipeResponse])
def read_recipes():
    return get_recipes()

@router.get("/{recipe_id}", response_model=RecipeResponse)
def read_recipe(recipe_id: int):
    recipe = get_recipe_by_id(recipe_id)

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe[0]

@router.post("/", response_model=List[RecipeResponse])
def add_recipe(recipe: RecipeCreate):
    return create_recipe(recipe.model_dump(mode="json"))

@router.patch("/{recipe_id}", response_model=List[RecipeResponse])
def update_recipe_route(recipe_id: int, recipe: RecipeUpdate):
    updated = update_recipe(recipe_id, recipe.model_dump(mode="json", exclude_unset=True))

    if not updated:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return updated

@router.delete("/{recipe_id}", response_model=List[RecipeResponse])
def delete_recipe_route(recipe_id: int):
    deleted = delete_recipe(recipe_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return deleted