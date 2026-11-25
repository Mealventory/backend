"""Server-side aggregation of current grocery store promotions for saved household stores."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from threading import Lock
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy import inspect, text

from app.core.auth_errors import AuthProblem
from app.schemas.promotions import (
    PromotionItemOut,
    StorePromotionStatusOut,
    StorePromotionsResponse,
)
from app.services import store_service

CACHE_TTL_SECONDS = 900.0
RATE_LIMIT_WINDOW_SECONDS = 60.0
HTTP_TIMEOUT_SECONDS = 5.0
USER_AGENT = "Mealventory/1.0 (+https://github.com/Mealventory)"


@dataclass(frozen=True)
class RetailerFeedAdapter:
    key: str
    display_name: str
    hosts: tuple[str, ...]
    aliases: tuple[str, ...]
    default_feed_url: str
    default_source_url: str


SUPPORTED_RETAILERS: tuple[RetailerFeedAdapter, ...] = (
    RetailerFeedAdapter(
        key="walmart",
        display_name="Walmart",
        hosts=("walmart.ca", "walmart.com"),
        aliases=("walmart", "walmart supercentre", "walmart supercenter"),
        default_feed_url="https://www.walmart.ca/api/promotions/weekly-flyer.json",
        default_source_url="https://www.walmart.ca/",
    ),
    RetailerFeedAdapter(
        key="costco",
        display_name="Costco",
        hosts=("costco.ca", "costco.com"),
        aliases=("costco", "costco wholesale"),
        default_feed_url="https://www.costco.ca/api/promotions/warehouse-savings.json",
        default_source_url="https://www.costco.ca/",
    ),
    RetailerFeedAdapter(
        key="nofrills",
        display_name="No Frills",
        hosts=("nofrills.ca",),
        aliases=("no frills", "nofrills"),
        default_feed_url="https://www.nofrills.ca/api/promotions/weekly-deals.json",
        default_source_url="https://www.nofrills.ca/",
    ),
    RetailerFeedAdapter(
        key="kroger",
        display_name="Kroger",
        hosts=("kroger.com",),
        aliases=("kroger",),
        default_feed_url="https://www.kroger.com/api/promotions/weekly-ad.json",
        default_source_url="https://www.kroger.com/",
    ),
)

_CACHE_LOCK = Lock()
_FEED_CACHE: dict[tuple[str, str], tuple[float, datetime, list[dict[str, Any]]]] = {}
_LAST_FETCH_AT: dict[tuple[str, str], float] = {}


def clear_promotion_cache() -> None:
    with _CACHE_LOCK:
        _FEED_CACHE.clear()
        _LAST_FETCH_AT.clear()


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def _configured_feed_urls() -> dict[str, str]:
    raw = os.getenv("PROMOTIONS_FEED_URLS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(k).strip().lower(): str(v).strip()
        for k, v in parsed.items()
        if isinstance(v, str) and v.strip().startswith(("http://", "https://"))
    }


def resolve_retailer_adapter(store_name: str, website_url: str | None) -> RetailerFeedAdapter | None:
    if website_url:
        host = (urlsplit(website_url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        for adapter in SUPPORTED_RETAILERS:
            if any(host == h or host.endswith(f".{h}") for h in adapter.hosts):
                return adapter

    normalized_name = re.sub(r"\s+", " ", (store_name or "").strip().lower())
    for adapter in SUPPORTED_RETAILERS:
        if any(alias in normalized_name for alias in adapter.aliases):
            return adapter
    return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _utc_now(value)
    if not isinstance(value, str):
        return None
    text_val = value.strip()
    if text_val.endswith("Z"):
        text_val = text_val[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text_val)
    except ValueError:
        return None
    return _utc_now(dt)


def _valid_http_url(candidate: Any, fallback: str | None) -> str | None:
    for value in (candidate, fallback):
        if isinstance(value, str):
            trimmed = value.strip()
            parsed = urlsplit(trimmed)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return trimmed
    return None


def _default_fetcher(adapter: RetailerFeedAdapter, feed_url: str) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = client.get(feed_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("promotions") or payload.get("items") or []
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    raise ValueError("Unsupported promotion feed payload")


def _normalize_tokens(text_value: str) -> set[str]:
    tokens = set()
    for raw in re.findall(r"[a-z0-9]+", (text_value or "").lower()):
        if len(raw) <= 1:
            continue
        tokens.add(raw)
        if len(raw) > 3 and raw.endswith("es"):
            tokens.add(raw[:-2])
        elif len(raw) > 2 and raw.endswith("s"):
            tokens.add(raw[:-1])
    return tokens


def _match_shopping_items(
    title: str,
    description: str | None,
    shopping_items: list[tuple[str, set[str]]],
) -> list[str]:
    if not shopping_items:
        return []
    promo_text = f"{title} {description or ''}".lower()
    promo_tokens = _normalize_tokens(promo_text)
    matched: list[str] = []
    for item_name, item_tokens in shopping_items:
        needle = item_name.strip().lower()
        if not needle:
            continue
        if needle in promo_text or (item_tokens and item_tokens <= promo_tokens):
            if item_name not in matched:
                matched.append(item_name)
    return matched


def _load_unchecked_shopping_items(db, household_id) -> list[tuple[str, set[str]]]:
    if not inspect(db.get_bind()).has_table("shopping_list_items"):
        return []
    rows = db.execute(
        text(
            "SELECT name FROM shopping_list_items "
            "WHERE household_id=:home AND is_checked=false "
            "ORDER BY created_at, id"
        ),
        {"home": str(household_id)},
    ).all()
    items: list[tuple[str, set[str]]] = []
    seen: set[str] = set()
    for (name,) in rows:
        clean = (name or "").strip()
        lowered = clean.lower()
        if clean and lowered not in seen:
            seen.add(lowered)
            items.append((clean, _normalize_tokens(clean)))
    return items


def _normalize_entries(
    raw_entries: list[dict[str, Any]],
    adapter: RetailerFeedAdapter,
    store: dict[str, Any],
    fetched_at: datetime,
    now: datetime,
    shopping_items: list[tuple[str, set[str]]],
) -> list[PromotionItemOut]:
    fallback_url = _valid_http_url(store.get("website_url"), adapter.default_source_url)
    normalized: list[PromotionItemOut] = []
    for idx, entry in enumerate(raw_entries):
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        source_url = _valid_http_url(entry.get("source_url"), fallback_url)
        if not source_url:
            continue
        valid_from = _parse_dt(entry.get("valid_from"))
        valid_until = _parse_dt(entry.get("valid_until"))
        if valid_until is not None and valid_until <= now:
            continue
        if valid_from is not None and valid_from > now:
            continue

        description_raw = entry.get("description")
        description = str(description_raw).strip() if description_raw is not None else None
        if description == "":
            description = None

        def _opt_str(key: str) -> str | None:
            val = entry.get(key)
            if val is None:
                return None
            trimmed = str(val).strip()
            return trimmed or None

        promo_id = str(entry.get("id") or f"{adapter.key}-{store['id']}-{idx}")
        matched = _match_shopping_items(title, description, shopping_items)
        normalized.append(
            PromotionItemOut(
                id=promo_id,
                retailer=adapter.display_name,
                store_id=store["id"],
                store_name=store["name"],
                title=title,
                description=description,
                promo_price=_opt_str("promo_price"),
                regular_price=_opt_str("regular_price"),
                discount_summary=_opt_str("discount_summary"),
                source_url=source_url,
                valid_from=valid_from,
                valid_until=valid_until,
                fetched_at=fetched_at,
                matched_shopping_items=matched,
            )
        )
    return normalized


def _fetch_store_promotions(
    adapter: RetailerFeedAdapter,
    store: dict[str, Any],
    now: datetime,
    fetcher: Callable[[RetailerFeedAdapter, str], list[dict[str, Any]]] | None,
    cache_ttl_seconds: float,
    rate_limit_window_seconds: float,
) -> tuple[list[dict[str, Any]], StorePromotionStatusOut]:
    overrides = _configured_feed_urls()
    feed_url = overrides.get(adapter.key, adapter.default_feed_url)
    cache_key = (adapter.key, feed_url)
    monotonic_now = time.monotonic()

    with _CACHE_LOCK:
        cached_entry = _FEED_CACHE.get(cache_key)
        if cached_entry is not None:
            cached_at_mono, fetched_at, raw_items = cached_entry
            if (monotonic_now - cached_at_mono) < cache_ttl_seconds:
                return raw_items, StorePromotionStatusOut(
                    store_id=store["id"],
                    store_name=store["name"],
                    retailer=adapter.display_name,
                    status="cached",
                    fetched_at=fetched_at,
                    cached=True,
                )

        last_attempt = _LAST_FETCH_AT.get(cache_key)
        if last_attempt is not None and (monotonic_now - last_attempt) < rate_limit_window_seconds:
            return [], StorePromotionStatusOut(
                store_id=store["id"],
                store_name=store["name"],
                retailer=adapter.display_name,
                status="rate_limited",
                fetched_at=None,
                cached=False,
                detail="Promotion feed rate-limited; try again shortly",
            )
        _LAST_FETCH_AT[cache_key] = monotonic_now

    fetch_fn = fetcher or _default_fetcher
    try:
        raw_items = fetch_fn(adapter, feed_url)
        if not isinstance(raw_items, list):
            raise ValueError("Invalid feed response")
        clean_items = [item for item in raw_items if isinstance(item, dict)]
    except Exception:
        return [], StorePromotionStatusOut(
            store_id=store["id"],
            store_name=store["name"],
            retailer=adapter.display_name,
            status="unavailable",
            fetched_at=None,
            cached=False,
            detail="Retailer promotions are temporarily unavailable",
        )

    with _CACHE_LOCK:
        _FEED_CACHE[cache_key] = (time.monotonic(), now, clean_items)

    return clean_items, StorePromotionStatusOut(
        store_id=store["id"],
        store_name=store["name"],
        retailer=adapter.display_name,
        status="ok",
        fetched_at=now,
        cached=False,
    )


def get_household_promotions(
    db,
    household_id,
    *,
    store_id=None,
    only_matched: bool = False,
    fetcher: Callable[[RetailerFeedAdapter, str], list[dict[str, Any]]] | None = None,
    now: datetime | None = None,
    cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    rate_limit_window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
) -> StorePromotionsResponse:
    current_time = _utc_now(now)
    saved_stores = [dict(row) for row in store_service.list_stores(db, household_id)]
    if store_id is not None:
        target = str(store_id)
        saved_stores = [s for s in saved_stores if str(s["id"]) == target]
        if not saved_stores:
            raise AuthProblem(404, "Store not found in this household")

    shopping_items = _load_unchecked_shopping_items(db, household_id)
    all_promotions: list[PromotionItemOut] = []
    store_statuses: list[StorePromotionStatusOut] = []

    for store in saved_stores:
        adapter = resolve_retailer_adapter(store.get("name", ""), store.get("website_url"))
        if adapter is None:
            store_statuses.append(
                StorePromotionStatusOut(
                    store_id=store["id"],
                    store_name=store["name"],
                    retailer=None,
                    status="unsupported",
                    detail="No maintained promotion feed for this store yet",
                )
            )
            continue

        raw_entries, status = _fetch_store_promotions(
            adapter,
            store,
            current_time,
            fetcher,
            cache_ttl_seconds,
            rate_limit_window_seconds,
        )
        store_statuses.append(status)
        if status.status in ("ok", "cached") and status.fetched_at is not None:
            normalized = _normalize_entries(
                raw_entries,
                adapter,
                store,
                status.fetched_at,
                current_time,
                shopping_items,
            )
            all_promotions.extend(normalized)

    if only_matched:
        all_promotions = [p for p in all_promotions if p.matched_shopping_items]

    all_promotions.sort(key=lambda p: (0 if p.matched_shopping_items else 1,))

    return StorePromotionsResponse(
        household_id=household_id,
        generated_at=current_time,
        promotions=all_promotions,
        stores=store_statuses,
    )
