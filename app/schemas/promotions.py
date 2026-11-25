from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PromotionItemOut(BaseModel):
    id: str
    retailer: str
    store_id: UUID
    store_name: str
    title: str
    description: str | None = None
    promo_price: str | None = None
    regular_price: str | None = None
    discount_summary: str | None = None
    source_url: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    fetched_at: datetime
    matched_shopping_items: list[str] = Field(default_factory=list)


class StorePromotionStatusOut(BaseModel):
    store_id: UUID
    store_name: str
    retailer: str | None = None
    status: Literal["ok", "cached", "unsupported", "unavailable", "rate_limited"]
    fetched_at: datetime | None = None
    cached: bool = False
    detail: str | None = None


class StorePromotionsResponse(BaseModel):
    household_id: UUID
    generated_at: datetime
    promotions: list[PromotionItemOut]
    stores: list[StorePromotionStatusOut]
