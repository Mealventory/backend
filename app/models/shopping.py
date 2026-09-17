"""Mapping of the existing DDL; constraints remain owned by init_db.sql."""
from uuid import uuid4
from sqlalchemy import Column, Uuid, Text, Numeric, Boolean, DateTime, func, false
from app.db.base import Base


class ShoppingListItem(Base):
    __tablename__ = 'shopping_list_items'
    id = Column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    household_id = Column(Uuid(as_uuid=False), nullable=False)
    food_id = Column(Uuid(as_uuid=False), nullable=True)
    name = Column(Text, nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, server_default='1')
    unit = Column(Text, nullable=False, server_default='units')
    checked = Column('is_checked', Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
