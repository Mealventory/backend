from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class ShoppingItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(default=Decimal('1'), gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(default='units', min_length=1, max_length=80)
    food_id: UUID | None = None


class ShoppingItemUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    checked: StrictBool | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one field to update')
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Updated fields cannot be null')
        return self


class ShoppingClaimRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ttl_minutes: int | None = Field(default=120, ge=1, le=480)


class ShoppingHandoffRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_user_id: UUID
    ttl_minutes: int | None = Field(default=120, ge=1, le=480)


class EndShoppingTripRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scope: Literal['mine', 'all'] = 'mine'


class EndShoppingTripOut(BaseModel):
    released_count: int


class ShoppingItemOut(BaseModel):
    id: UUID
    household_id: UUID
    food_id: UUID | None
    name: str
    quantity: Decimal
    unit: str
    checked: bool
    claimed_by: UUID | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ClearCheckedOut(BaseModel):
    deleted_count: int
