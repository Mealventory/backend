from typing import List, Literal
from pydantic import BaseModel, Field

class ManualItemInput(BaseModel):
	name: str
	quantity: int = 1
	freezer_count: int = 0

class SampleScanRequest(BaseModel):
	sample_name: str
	mode: Literal["food", "receipt", "tag", "recipt"] = "food"
	persist_to_db: bool = False
	user_id: str | None = None
	freezer_counts: dict[str, int] = Field(default_factory=dict)
	manual_items: List[ManualItemInput] = Field(default_factory=list)
