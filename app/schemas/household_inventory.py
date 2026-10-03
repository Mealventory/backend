from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator, BeforeValidator

ItemStatus = Literal['active', 'consumed', 'discarded']

def validate_image_ref(value):
    if not isinstance(value, str):
        raise ValueError('Image reference must be a string')
    value = value.strip()
    if not value:
        raise ValueError('Image reference cannot be empty')
    if len(value) > 2048:
        raise ValueError('Image reference is too long')
    if value.startswith('https://'):
        return value
    if '://' in value or value.startswith('/'):
        raise ValueError('Image reference must be an HTTPS URL or private storage path')
    parts = value.split('/')
    if len(parts) < 2 or any(part in ('', '.', '..') for part in parts):
        raise ValueError('Invalid private image storage path')
    return value

ImageRef = Annotated[str, BeforeValidator(validate_image_ref)]

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
    unit: str = Field(default='units', min_length=1, max_length=80)
    expiry_date: date | None = None
    storage_location_id: UUID | None = None

    storage_zone: StorageZone = 'pantry'
    image_ref: ImageRef | None = None

    @model_validator(mode='after')
    def validate_storage(self):
        if 'storage_zone' in self.model_fields_set and self.storage_location_id is not None:
            raise ValueError('Provide storage_zone or storage_location_id, not both')
        return self


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    storage_zone: StorageZone | None = None
    image_ref: str | None = None
    status: ItemStatus | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    expiry_date: date | None = None
    storage_location_id: UUID | None = None
    image_ref: ImageRef | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one field to update')
        for field in ('quantity', 'unit', 'name', 'category', 'storage_zone', 'status'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} cannot be null')
        if {'storage_zone', 'storage_location_id'} <= self.model_fields_set:
            raise ValueError('Provide storage_zone or storage_location_id, not both')
        return self


class ItemOut(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    category: str | None
    quantity: Decimal
    remaining_percent: Decimal | None = None
    is_low_stock: bool = False
    unit: str
    expiry_date: date | None
    status: ItemStatus
    storage_location_id: UUID | None = None
    storage_zone: StorageZone | None = None
