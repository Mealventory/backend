from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import verify_firebase_token
from app.dependencies.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer()


def get_current_user(
	credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
	db: Session = Depends(get_db),
) -> User:
	token_data = verify_firebase_token(credentials.credentials)
	uid = token_data["uid"]

	user = db.query(User).filter(User.id == uid).first()
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not registered. Please call /users/register first.",
		)
	return user
