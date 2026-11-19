
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


ActivityAction = Literal[
    "added",
    "updated",
    "moved",
    "consumed",
    "discarded",
    "deleted",
    "shopping_added",
]

ActivityEntityType = Literal["inventory", "shopping"]

WasteReason = Literal[
    "expired",
    "spoiled",
    "bought_too_much",
    "didnt_like",
    "other",
]


class ActivityEventOut(BaseModel):
    id: UUID
    household_id: UUID
    actor_user_id: UUID
    actor_name: str
    action: ActivityAction
    entity_type: ActivityEntityType
    entity_id: UUID | None = None
    item_name: str
    reason: WasteReason | None = None
    created_at: datetime
