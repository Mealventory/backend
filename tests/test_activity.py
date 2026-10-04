"""Household activity API behavior and tenant isolation."""
from sqlalchemy import text

from tests.test_household_inventory import (
    HOME,
    MEMBER,
    OTHER,
    OUTSIDER,
    inventory_api,
)


PATH = "/api/v1/activity"
HOME_HEADERS = {"X-Household-ID": HOME}
OTHER_HEADERS = {"X-Household-ID": OTHER}


def test_activity_records_mutations_newest_first_and_opens_active_items(inventory_api):
    client, identity, _ = inventory_api

    milk = client.post(
        "/api/v1/items",
        headers=HOME_HEADERS,
        json={"name": "Milk", "storage_zone": "fridge"},
    )
    assert milk.status_code == 201, milk.text
    milk_id = milk.json()["id"]

    identity["id"] = MEMBER
    moved = client.patch(
        f"/api/v1/items/{milk_id}",
        headers=HOME_HEADERS,
        json={"storage_zone": "pantry"},
    )
    assert moved.status_code == 200, moved.text

    consumed = client.post(
        f"/api/v1/items/{milk_id}/consume",
        headers=HOME_HEADERS,
    )
    assert consumed.status_code == 200, consumed.text

    events = client.get(PATH, headers=HOME_HEADERS).json()
    assert [event["action"] for event in events[:3]] == [
        "consumed",
        "moved",
        "added",
    ]
    assert all(event["item_name"] == "Milk" for event in events[:3])
    assert all(event["household_id"] == HOME for event in events)
    assert events[0]["actor_user_id"] == MEMBER
    assert events[0]["actor_name"] == "Test"
    assert events[2]["entity_id"] == milk_id


def test_activity_is_household_scoped_and_limit_is_bounded(inventory_api):
    client, identity, engine = inventory_api

    client.post("/api/v1/items", headers=HOME_HEADERS, json={"name": "Rice"})

    identity["id"] = OUTSIDER
    client.post("/api/v1/items", headers=OTHER_HEADERS, json={"name": "Beans"})

    assert [event["item_name"] for event in client.get(PATH, headers=OTHER_HEADERS).json()] == ["Beans"]

    identity["id"] = MEMBER
    home_events = client.get(PATH, headers=HOME_HEADERS).json()
    assert [event["item_name"] for event in home_events] == ["Rice"]

    assert client.get(PATH + "?limit=0", headers=HOME_HEADERS).status_code == 422
    assert client.get(PATH + "?limit=101", headers=HOME_HEADERS).status_code == 422

    with engine.connect() as db:
        assert db.execute(
            text("SELECT count(*) FROM household_activity_events")
        ).scalar() == 2


def test_failed_inventory_mutation_does_not_create_activity(inventory_api):
    client, _, engine = inventory_api
    response = client.post(
        "/api/v1/items",
        headers=HOME_HEADERS,
        json={"name": ""},
    )
    assert response.status_code == 422
    assert client.get(PATH, headers=HOME_HEADERS).json() == []
    with engine.connect() as db:
        assert db.execute(
            text("SELECT count(*) FROM household_activity_events")
        ).scalar() == 0
