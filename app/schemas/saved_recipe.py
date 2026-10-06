from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

ShortText = Annotated[str, Field(min_length=1, max_length=300)]


class RecipeSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: ShortText
    name: ShortText
    time: ShortText
    difficulty: Literal['Easy', 'Medium', 'Hard']
    match: float = Field(ge=0, le=100)
    uses: list[ShortText] = Field(max_length=100)
    emoji: str = Field(max_length=32)
    tag: str = Field(max_length=100)
    description: str = Field(max_length=10000)
    steps: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(max_length=100)
    priorityIngredients: list[ShortText] | None = Field(default=None, max_length=100)
    missingIngredients: list[ShortText] | None = Field(default=None, max_length=100)
