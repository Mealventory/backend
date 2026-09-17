from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

ItemStatus = Literal['active', 'consumed', 'discarded']
StorageZone = Literal['pantry', 'fridge', 'freezer', 'spicerack']


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default='Pantry', min_length=1, max_length=80)
    quantity: Decimal = Field(default=Decimal('1'), gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(default='units', min_length=1, max_length=80)
    expiry_date: date | None = None
    storage_location_id: UUID | None = None


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    expiry_date: date | None = None
    storage_location_id: UUID | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one field to update')
        for field in ('quantity', 'unit'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} cannot be null')
        return self


class ItemOut(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    category: str | None
    quantity: Decimal
    unit: str
    expiry_date: date | None
    status: ItemStatus
    storage_location_id: UUID | None = None
