from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecipeInventoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    days_until_expiry: int | None = Field(default=None, ge=0)


class RecipeGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority_items: list[RecipeInventoryItem]
    other_items: list[RecipeInventoryItem]


class RecipeSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    uses_priority_items: list[str]
    uses_other_items: list[str]
    optional_pantry_basics: list[str]
    prep_time_minutes: int = Field(ge=0, le=1440)
    cook_time_minutes: int = Field(ge=0, le=1440)
    difficulty: Literal["Easy", "Medium", "Hard"]
    steps: list[str] = Field(min_length=1, max_length=30)
    waste_reduction_reason: str


class RecipeProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipes: list[RecipeSuggestion] = Field(min_length=1, max_length=5)


class RecipeSuggestionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipes: list[RecipeSuggestion] = Field(default_factory=list, max_length=5)
    priority_items: list[RecipeInventoryItem] = Field(default_factory=list)
