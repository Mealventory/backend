from uuid import UUID
from app.core.dependencies import get_current_household
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.schemas.user import UserOut
from app.services.recipe_service import get_inventory_recipes

router = APIRouter()


@router.get("/")
async def get_recipes(
	current_user: UserOut = Depends(get_current_user),
	household_id: UUID = Depends(get_current_household),
	db: Session = Depends(get_db),
):
    """Return recipe suggestions for the current inventory."""
    return await get_inventory_recipes(household_id, db)


from app.schemas.saved_recipe import RecipeSnapshot
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
