from typing import Literal

from pydantic import BaseModel, Field


class PantryImportChoice(BaseModel):
    row: int = Field(ge=2)
    action: Literal["skip", "add", "merge"]


class PantryImportConfirm(BaseModel):
    operation_id: str = Field(min_length=20, max_length=100_000)
    choices: list[PantryImportChoice] = Field(max_length=100)
