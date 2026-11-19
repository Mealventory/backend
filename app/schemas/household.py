from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

MemberRole = Literal["owner", "admin", "member"]


class HouseholdCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class HouseholdJoin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invite_code: str = Field(pattern=r"^[A-Z0-9]{6}$")

    @field_validator("invite_code", mode="before")
    @classmethod
    def normalize_code(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: MemberRole


class HouseholdOut(BaseModel):
    id: UUID
    name: str
    invite_code: str | None
    role: MemberRole


class HouseholdMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    household_id: UUID
    user_id: UUID
    role: MemberRole
    display_name: str | None = None
    username: str | None = None
