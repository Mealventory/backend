from pydantic import BaseModel, Field
from typing import List


class GeneratedRecipe(BaseModel):
    title: str
    uses_priority_items: List[str]
    uses_other_items: List[str]
    optional_pantry_basics: List[str] = Field(default_factory=list)
    prep_time_minutes: int
    cook_time_minutes: int
    difficulty: str
    steps: List[str]
    waste_reduction_reason: str


class GeneratedRecipeResponse(BaseModel):
    recipes: List[GeneratedRecipe]