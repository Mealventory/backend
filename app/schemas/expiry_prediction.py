from datetime import date
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from app.schemas.household_inventory import StorageZone

class ExpiryPredictionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    storage_zone: StorageZone
    purchase_date: date
    item_id: UUID | None = None
    avg_shelf_life_days: int | None = Field(default=None, ge=5, le=30)

    @model_validator(mode='after')
    def validate_purchase_date(self):
        if self.purchase_date > date.today():
            raise ValueError('Purchase date cannot be in the future')
        return self

class ExpiryPredictionOutput(BaseModel):
    predicted_expiry_date: date | None = None
    source: Literal['model', 'unavailable']
    explanation: str
    purchase_date: date
    temperature: float | None = None
    humidity: float | None = None
    baseline_source: Literal['provided', 'catalog'] | None = None
