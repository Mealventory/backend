from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.services import auth_service
from app.dependencies.auth import bearer_scheme, get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.user import UserOut
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """Sync a Firebase-authenticated user into the database."""
    return auth_service.register_user(credentials.credentials, db)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
