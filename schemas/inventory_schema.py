from pydantic import BaseModel
from typing import Optional
from datetime import date

class InventoryCreate(BaseModel):
    user_id: int
    food_item_id: int
    quantity: float
    unit: Optional[str] = None
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    storage_location: Optional[str] = None
    status: Optional[str] = "fresh"

class InventoryUpdate(BaseModel):
    user_id: Optional[int] = None
    food_item_id: Optional[int] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    storage_location: Optional[str] = None
    status: Optional[str] = None