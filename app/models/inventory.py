# models/inventory_item.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, timezone
from app.db.base import Base

class InventoryItem(Base):

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    food_id = Column(Integer, ForeignKey("foods.id"))
    date_added = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expiry_date = Column(DateTime)
    status = Column(String, default="fresh")