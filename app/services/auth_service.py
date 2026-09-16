"""Optional legacy profile synchronization; Supabase owns authentication."""
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserOut


def register_user(current_user: UserOut, db: Session):
    existing = db.query(User).filter(User.id == current_user.id).first()
    if existing:
        return existing
    user = User(id=current_user.id, email=current_user.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
