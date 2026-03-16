from pydantic import BaseModel


class FoodOut(BaseModel):
	id: int
	name: str
	type: str | None
	subtype: str | None
	avg_shelf_life_days: int | None

	model_config = {"from_attributes": True}
