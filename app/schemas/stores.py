from datetime import datetime
from uuid import UUID
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class HouseholdStoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    website_url: AnyHttpUrl | None = None


class HouseholdStoreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    website_url: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Store name cannot be null")
        return self


class HouseholdStoreReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("store_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Store IDs must be unique")
        return value


class HouseholdStoreOut(BaseModel):
    id: UUID
    household_id: UUID
    name: str
    website_url: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
