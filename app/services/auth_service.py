from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.core.security import verify_firebase_token
from app.models.user import User

def register_user(token: str, db: Session):
    'Sync a Firebase-authenticated user into the database.'
    token_data = verify_firebase_token(token)
    uid = token_data['uid']
    email = token_data.get('email', '')
    existing = db.query(User).filter(User.id == uid).first()
    if existing:
        return existing
    user = User(id=uid, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_registered_user(token: str, db: Session) -> User:
    token_data = verify_firebase_token(token)
    user = db.query(User).filter(User.id == token_data["uid"]).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User not registered. Please call /api/v1/users/register first.")
    return user
