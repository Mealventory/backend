from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class IngredientDeduction(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    expected_quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(min_length=1, max_length=80)


class RecipeCompletion(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    completion_id: str = Field(min_length=16, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    recipe_id: str = Field(min_length=1, max_length=200)
    recipe_name: str = Field(min_length=1, max_length=200)
    items: list[IngredientDeduction] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_items(self):
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError('Review each pantry item only once')
        return self
