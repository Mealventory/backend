"""Device registration only; notification delivery is a separate service."""
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.core.dependencies import get_current_user
from app.dependencies.database import get_db
from app.schemas.user import UserOut
from app.models.push_token import PushToken

router = APIRouter()

class TokenBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(max_length=255, pattern=r'^(ExpoPushToken|ExponentPushToken)\[[A-Za-z0-9_-]+\]$')

class Registration(TokenBody):
    platform: Literal['ios', 'android']

@router.put('/device', status_code=204)
def register_device(body: Registration, user: UserOut = Depends(get_current_user), db: Session = Depends(get_db)):
    # A token has one owner. Signing in on the same phone transfers it atomically.
    insert = sqlite_insert if db.bind.dialect.name == 'sqlite' else pg_insert
    stmt = insert(PushToken).values(user_id=user.id, token=body.token, platform=body.platform)
    stmt = stmt.on_conflict_do_update(index_elements=['token'], set_={
        'user_id': user.id, 'platform': body.platform, 'updated_at': func.now()})
    try:
        db.execute(stmt); db.commit()
    except Exception:
        db.rollback(); raise

@router.post('/device/remove', status_code=204)
def remove_device(body: TokenBody, user: UserOut = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        db.query(PushToken).filter_by(user_id=user.id, token=body.token).delete()
        db.commit()
    except Exception:
        db.rollback(); raise
