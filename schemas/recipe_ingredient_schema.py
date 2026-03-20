from pydantic import BaseModel
from typing import Optional

class RecipeIngredientCreate(BaseModel):
    food_item_id: int
    quantity: float
    unit: Optional[str] = None

class RecipeIngredientUpdate(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None