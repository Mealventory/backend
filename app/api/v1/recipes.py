from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_household
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.schemas.recipe_suggestion import RecipeSuggestionsResponse
from app.schemas.user import UserOut
from app.services.recipe_service import get_inventory_recipes

router = APIRouter()


@router.get("/", response_model=RecipeSuggestionsResponse)
async def get_recipes(
    current_user: UserOut = Depends(get_current_user),
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Return recipe suggestions generated directly by the backend recipe provider."""
    return await get_inventory_recipes(household_id, db)


from app.schemas.saved_recipe import RecipeSnapshot, SavedRecipeUpdate
from app.services import saved_recipe_service


@router.get('/saved', response_model=list[RecipeSnapshot])
def list_saved_recipes(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    return saved_recipe_service.list_saved(db, household_id)


@router.put('/saved', status_code=204)
def save_household_recipe(recipe: RecipeSnapshot, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    saved_recipe_service.save(db, household_id, recipe)


@router.post('/saved/remove', status_code=204)
def remove_household_recipe(recipe: RecipeSnapshot, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    saved_recipe_service.remove(db, household_id, recipe)


@router.put('/saved/update', status_code=204)
def update_household_recipe(request: SavedRecipeUpdate, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    result = saved_recipe_service.update(db, household_id, request.previous, request.recipe)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail='The saved recipe could not be found. Refresh Saved recipes and try again.')
    if result == 'duplicate':
        raise HTTPException(status_code=409, detail='Another saved recipe already has this name and ingredients.')


from app.schemas.recipe_completion import RecipeCompletion
from app.services.recipe_completion_service import complete_recipe


@router.post('/complete')
def finish_recipe(request: RecipeCompletion, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Atomically deduct reviewed ingredients; reuse completion_id for retries."""
    return complete_recipe(db, household_id, request)
