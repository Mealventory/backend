from pydantic import BaseModel
from typing import Optional

class FoodItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    default_unit: Optional[str] = None
    barcode: Optional[str] = None
    typical_shelf_life_days: Optional[int] = None

class FoodItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    default_unit: Optional[str] = None
    barcode: Optional[str] = None
    typical_shelf_life_days: Optional[int] = None