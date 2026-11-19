"""Validated, household-scoped meal plan API contract."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.saved_recipe import RecipeSnapshot

MealSlotName = Literal["lunch", "dinner"]


class MealPlanEntry(BaseModel):
    date: date
    slot: MealSlotName
    recipe: RecipeSnapshot
    revision: int = Field(ge=1)


class MealPlanState(BaseModel):
    meals: list[MealPlanEntry]
    slot_versions: dict[str, int]
    imported_local_plan: bool


class MealPlanAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    slot: MealSlotName
    recipe: RecipeSnapshot
    expected_revision: int = Field(ge=0)


class MealPlanRemove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    slot: MealSlotName
    expected_revision: int = Field(ge=0)


class MealPlanMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_date: date
    source_slot: MealSlotName
    target_date: date
    target_slot: MealSlotName
    source_revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)


class LocalMeal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    slot: MealSlotName
    recipe: RecipeSnapshot
    expected_revision: int = Field(ge=0)


class MealPlanImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    import_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    meals: list[LocalMeal] = Field(min_length=1, max_length=180)


class ImportCandidate(BaseModel):
    date: date
    slot: MealSlotName
    status: Literal["available", "occupied"]
    revision: int


class MealPlanImportPreview(BaseModel):
    candidates: list[ImportCandidate]
    imported_local_plan: bool
