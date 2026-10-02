from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator, BeforeValidator

ItemStatus = Literal['active', 'consumed', 'discarded']
def validate_storage_zone(value):
    if value not in ('pantry', 'fridge', 'freezer', 'spicerack'):
        from app.core.auth_errors import AuthProblem
        raise AuthProblem(400, 'Storage zone must be pantry, fridge, freezer or spicerack')
    return value


StorageZone = Annotated[Literal['pantry', 'fridge', 'freezer', 'spicerack'], BeforeValidator(validate_storage_zone)]


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default='Pantry', min_length=1, max_length=80)
    quantity: Decimal = Field(default=Decimal('1'), gt=0, max_digits=12, decimal_places=3)
    quantity_tracking_enabled: bool = False
    initial_quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    low_stock_threshold_percent: Decimal = Field(default=Decimal('10'), gt=0, le=100, max_digits=5, decimal_places=2)
    unit: str = Field(default='units', min_length=1, max_length=80)
    expiry_date: date | None = None
    storage_location_id: UUID | None = None

    storage_zone: StorageZone = 'pantry'

    @model_validator(mode='after')
    def validate_storage(self):
        if 'storage_zone' in self.model_fields_set and self.storage_location_id is not None:
            raise ValueError('Provide storage_zone or storage_location_id, not both')
        if self.quantity_tracking_enabled:
            if self.initial_quantity is None:
                self.initial_quantity = self.quantity
        elif self.initial_quantity is not None:
            raise ValueError('initial_quantity requires quantity_tracking_enabled')
        return self


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    storage_zone: StorageZone | None = None
    status: ItemStatus | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    quantity_tracking_enabled: bool | None = None
    initial_quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    low_stock_threshold_percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    expiry_date: date | None = None
    storage_location_id: UUID | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one field to update')
        for field in ('quantity', 'unit', 'name', 'category', 'storage_zone', 'status',
                      'quantity_tracking_enabled', 'low_stock_threshold_percent'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} cannot be null')
        if self.quantity_tracking_enabled is False and 'initial_quantity' in self.model_fields_set and self.initial_quantity is not None:
            raise ValueError('initial_quantity cannot be set when quantity tracking is disabled')
        if {'storage_zone', 'storage_location_id'} <= self.model_fields_set:
            raise ValueError('Provide storage_zone or storage_location_id, not both')
        return self


class ItemOut(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    category: str | None
    quantity: Decimal
    quantity_tracking_enabled: bool = False
    initial_quantity: Decimal | None = None
    low_stock_threshold_percent: Decimal = Decimal('10')
    remaining_percent: Decimal | None = None
    is_low_stock: bool = False
    unit: str
    expiry_date: date | None
    status: ItemStatus
    storage_location_id: UUID | None = None
    storage_zone: StorageZone | None = None
