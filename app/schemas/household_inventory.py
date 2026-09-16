from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default='Pantry', min_length=1, max_length=80)
    quantity: Decimal = Field(default=Decimal('1'), gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(default='units', min_length=1, max_length=80)
    expiry_date: date | None = None


class ItemOut(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    category: str | None
    quantity: Decimal
    unit: str
    expiry_date: date | None
    status: str
