from datetime import datetime
from pydantic import BaseModel


class InventoryItemCreate(BaseModel):
	food_id: int
	expiry_date: datetime | None = None


class InventoryItemOut(BaseModel):
	id: int
	user_id: str
	food_id: int
	date_added: datetime
	expiry_date: datetime | None
	status: str

	model_config = {"from_attributes": True}
