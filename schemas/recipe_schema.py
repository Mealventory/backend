from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class RecipeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    servings: Optional[int] = None

class RecipeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    servings: Optional[int] = None

class RecipeIngredientResponse(BaseModel):
    food_item_id: int
    quantity: float
    unit: Optional[str] = None
    food_items: Optional[dict] = None

class RecipeResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    servings: Optional[int] = None
    created_at: datetime
    recipe_ingredients: Optional[List[RecipeIngredientResponse]] = None