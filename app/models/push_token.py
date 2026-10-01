from uuid import uuid4
from sqlalchemy import Column, Uuid, Text, DateTime, func
from app.db.base import Base

class PushToken(Base):
    __tablename__ = 'device_push_tokens'
    id = Column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(Uuid(as_uuid=False), nullable=False, index=True)
    token = Column(Text, nullable=False, unique=True)
    platform = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
