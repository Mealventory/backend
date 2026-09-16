from uuid import uuid4
from sqlalchemy import Column, DateTime, String, Uuid, func
from app.db.base import Base


class Household(Base):
    __tablename__ = "households"
    id = Column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, nullable=False)
    created_by = Column(Uuid(as_uuid=False), nullable=False)
    invite_code = Column(String(6), unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
