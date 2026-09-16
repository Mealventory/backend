from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.services.recipe_service import get_inventory_recipes

router = APIRouter()


@router.get("/")
async def get_recipes(
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
    """Return recipe suggestions for the current inventory."""
    return await get_inventory_recipes(current_user, db)
