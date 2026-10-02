"""Mapping of the household store DDL; constraints remain owned by SQL scripts."""
from uuid import uuid4
from sqlalchemy import Column, Uuid, Text, Integer, DateTime, func
from app.db.base import Base


class HouseholdStore(Base):
    __tablename__ = "household_stores"

    id = Column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    household_id = Column(Uuid(as_uuid=False), nullable=False)
    name = Column(Text, nullable=False)
    website_url = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
