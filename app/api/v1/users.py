from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_firebase_token
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
    token_data = verify_firebase_token(credentials.credentials)
    uid = token_data["uid"]
    email = token_data.get("email", "")

    existing = db.query(User).filter(User.id == uid).first()
    if existing:
        return existing

    user = User(id=uid, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
