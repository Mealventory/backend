"""Tests for household store sales & promotions aggregation (#103)."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.dependencies import get_current_user
from app.main import app
from app.models.household_store import HouseholdStore
from app.models.shopping import ShoppingListItem
from app.services import promotions_service
from tests.test_household_inventory import (
    HOME,
    OTHER,
    OUTSIDER,
    inventory_api,
)

STORES_PATH = "/api/v1/stores"
PROMOTIONS_PATH = "/api/v1/stores/promotions"
SHOPPING_PATH = "/api/v1/shopping"
HEADERS = {"X-Household-ID": HOME}


@pytest.fixture
def promotions_api(inventory_api):
    client, identity, engine = inventory_api
    HouseholdStore.__table__.create(engine)
    ShoppingListItem.__table__.create(engine)
    promotions_service.clear_promotion_cache()
    yield client, identity, engine
    promotions_service.clear_promotion_cache()


def test_supported_retailer_promotions_and_shopping_matching(promotions_api, monkeypatch):
    client, _, _ = promotions_api
    walmart = client.post(
        STORES_PATH,
        headers=HEADERS,
        json={"name": "Walmart", "website_url": "https://www.walmart.ca/"},
    ).json()
    local_bakery = client.post(
        STORES_PATH,
        headers=HEADERS,
        json={"name": "Corner Bakery", "website_url": "https://cornerbakery.example/"},
    ).json()

    assert client.post(SHOPPING_PATH, headers=HEADERS, json={"name": "Whole Milk"}).status_code == 201
    assert client.post(SHOPPING_PATH, headers=HEADERS, json={"name": "Eggs"}).status_code == 201
    checked_item = client.post(SHOPPING_PATH, headers=HEADERS, json={"name": "Bananas"}).json()
    assert client.patch(f"{SHOPPING_PATH}/{checked_item['id']}", headers=HEADERS, json={"checked": True}).status_code == 200

    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    def fake_fetcher(adapter, feed_url):
        assert adapter.key == "walmart"
        return [
            {
                "id": "p-bread",
                "title": "Artisan Sourdough Loaf",
                "description": "Fresh bakery loaf",
                "promo_price": "$3.49",
                "regular_price": "$4.99",
                "source_url": "https://www.walmart.ca/deals/bread",
                "valid_until": future,
            },
            {
                "id": "p-milk",
                "title": "Organic Whole Milk 4L",
                "description": "Dairy weekly special",
                "promo_price": "$5.99",
                "source_url": "https://www.walmart.ca/deals/milk",
                "valid_until": future,
            },
            {
                "id": "p-bananas",
                "title": "Bananas Bunch",
                "promo_price": "$1.29",
                "source_url": "https://www.walmart.ca/deals/bananas",
                "valid_until": future,
            },
            {
                "id": "p-expired",
                "title": "Expired Egg Promo",
                "description": "Free range eggs",
                "promo_price": "$2.99",
                "source_url": "https://www.walmart.ca/deals/eggs",
                "valid_until": past,
            },
        ]

    monkeypatch.setattr(promotions_service, "_default_fetcher", fake_fetcher)

    resp = client.get(PROMOTIONS_PATH, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["household_id"] == HOME
    assert body["generated_at"]

    # Expired promo excluded; matched Whole Milk sorted first; checked Bananas not matched
    titles = [p["title"] for p in body["promotions"]]
    assert titles == [
        "Organic Whole Milk 4L",
        "Artisan Sourdough Loaf",
        "Bananas Bunch",
    ]
    milk_promo = body["promotions"][0]
    assert milk_promo["retailer"] == "Walmart"
    assert milk_promo["store_id"] == walmart["id"]
    assert milk_promo["source_url"] == "https://www.walmart.ca/deals/milk"
    assert milk_promo["promo_price"] == "$5.99"
    assert milk_promo["fetched_at"]
    assert milk_promo["matched_shopping_items"] == ["Whole Milk"]

    statuses = {s["store_id"]: s for s in body["stores"]}
    assert statuses[walmart["id"]]["status"] == "ok"
    assert statuses[walmart["id"]]["cached"] is False
    assert statuses[local_bakery["id"]]["status"] == "unsupported"

    # only_matched=true returns only matched promos, and uses cache
    matched_only = client.get(f"{PROMOTIONS_PATH}?only_matched=true&store_id={walmart['id']}", headers=HEADERS)
    assert matched_only.status_code == 200
    matched_body = matched_only.json()
    assert [p["title"] for p in matched_body["promotions"]] == ["Organic Whole Milk 4L"]
    assert matched_body["stores"][0]["status"] == "cached"
    assert matched_body["stores"][0]["cached"] is True


def test_cache_and_rate_limit_and_graceful_failure(promotions_api, monkeypatch):
    client, _, _ = promotions_api
    costco = client.post(
        STORES_PATH,
        headers=HEADERS,
        json={"name": "Costco", "website_url": "https://www.costco.ca/"},
    ).json()
    walmart = client.post(
        STORES_PATH,
        headers=HEADERS,
        json={"name": "Walmart", "website_url": "https://www.walmart.ca/"},
    ).json()
    assert client.post(SHOPPING_PATH, headers=HEADERS, json={"name": "Coffee"}).status_code == 201

    calls = {"costco": 0, "walmart": 0}

    def flaky_fetcher(adapter, feed_url):
        calls[adapter.key] += 1
        if adapter.key == "walmart":
            raise httpx.ConnectTimeout("upstream timeout")
        return [
            {
                "id": "c-1",
                "title": "Kirkland Coffee Beans",
                "promo_price": "$14.99",
                "source_url": "https://www.costco.ca/coffee",
            }
        ]

    monkeypatch.setattr(promotions_service, "_default_fetcher", flaky_fetcher)

    first = client.get(PROMOTIONS_PATH, headers=HEADERS)
    assert first.status_code == 200
    first_body = first.json()
    assert [p["title"] for p in first_body["promotions"]] == ["Kirkland Coffee Beans"]
    statuses = {s["store_id"]: s for s in first_body["stores"]}
    assert statuses[costco["id"]]["status"] == "ok"
    assert statuses[walmart["id"]]["status"] == "unavailable"

    # Second call: costco comes from cache, walmart is rate-limited instead of hammering upstream
    second = client.get(PROMOTIONS_PATH, headers=HEADERS)
    assert second.status_code == 200
    statuses2 = {s["store_id"]: s for s in second.json()["stores"]}
    assert statuses2[costco["id"]]["status"] == "cached"
    assert statuses2[walmart["id"]]["status"] == "rate_limited"
    assert calls == {"costco": 1, "walmart": 1}

    # Core shopping functionality continues unaffected
    assert client.get(SHOPPING_PATH, headers=HEADERS).status_code == 200


def test_promotions_household_isolation_and_auth(promotions_api, monkeypatch):
    client, identity, _ = promotions_api
    own = client.post(STORES_PATH, headers=HEADERS, json={"name": "Costco"}).json()
    monkeypatch.setattr(promotions_service, "_default_fetcher", lambda adapter, url: [])

    identity["id"] = OUTSIDER
    assert client.get(PROMOTIONS_PATH, headers=HEADERS).status_code == 403

    other_headers = {"X-Household-ID": OTHER}
    assert client.get(f"{PROMOTIONS_PATH}?store_id={own['id']}", headers=other_headers).status_code == 404
    assert client.get(PROMOTIONS_PATH, headers=other_headers).json()["stores"] == []

    assert client.get(PROMOTIONS_PATH).status_code == 400
    app.dependency_overrides.pop(get_current_user)
    assert client.get(PROMOTIONS_PATH, headers=HEADERS).status_code == 401
