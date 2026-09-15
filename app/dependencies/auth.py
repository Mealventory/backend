from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.services import auth_service
from app.dependencies.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer()


def get_current_user(
	credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
	db: Session = Depends(get_db),
) -> User:
    return auth_service.get_registered_user(credentials.credentials, db)
