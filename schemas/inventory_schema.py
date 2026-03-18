from pydantic import BaseModel
from typing import Optional

class InventoryCreate(BaseModel):
    user_id: int
    food_item_id: int
    quantity: float
    unit: Optional[str] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    storage_location: Optional[str] = None
    status: Optional[str] = "fresh"