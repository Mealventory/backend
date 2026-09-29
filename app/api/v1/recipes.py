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
