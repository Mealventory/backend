from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.services import auth_service
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.schemas.user import UserOut

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync a Supabase-authenticated user into the database."""
    return auth_service.register_user(current_user, db)


@router.get("/me", response_model=UserOut)
def get_me(current_user: UserOut = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
