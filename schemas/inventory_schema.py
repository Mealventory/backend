from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class InventoryCreate(BaseModel):
    user_id: int
    food_item_id: int
    quantity: float
    unit: Optional[str] = None
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    storage_location: Optional[str] = None

class InventoryUpdate(BaseModel):
    user_id: Optional[int] = None
    food_item_id: Optional[int] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    storage_location: Optional[str] = None

class FoodItemResponse(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    default_unit: Optional[str] = None
    barcode: Optional[str] = None
    typical_shelf_life_days: Optional[int] = None

class InventoryResponse(BaseModel):
    id: int
    user_id: int
    food_item_id: int
    quantity: float
    unit: Optional[str] = None
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    storage_location: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    food_items: Optional[FoodItemResponse] = None