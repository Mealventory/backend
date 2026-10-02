"""Household frequently shopped stores API tests."""
import pytest
from sqlalchemy import text

from app.core.dependencies import get_current_user
from app.main import app
from app.models.household_store import HouseholdStore
from tests.test_household_inventory import (
    HOME,
    MEMBER,
    OTHER,
    OUTSIDER,
    OWNER,
    inventory_api,
)

PATH = "/api/v1/stores"
HEADERS = {"X-Household-ID": HOME}


@pytest.fixture
def stores_api(inventory_api):
    client, identity, engine = inventory_api
    HouseholdStore.__table__.create(engine)
    return client, identity, engine


def test_household_members_share_crud_and_user_order(stores_api):
    client, identity, engine = stores_api

    costco = client.post(
        PATH,
        headers=HEADERS,
        json={"name": " Costco ", "website_url": "https://www.costco.ca/"},
    )
    walmart = client.post(
        PATH,
        headers=HEADERS,
        json={"name": "Walmart", "website_url": "https://www.walmart.ca/"},
    )
    assert costco.status_code == 201, costco.text
    assert walmart.status_code == 201, walmart.text

    costco_row = costco.json()
    walmart_row = walmart.json()
    assert costco_row["name"] == "Costco"
    assert costco_row["sort_order"] == 0
    assert walmart_row["sort_order"] == 1

    identity["id"] = MEMBER
    assert [row["id"] for row in client.get(PATH, headers=HEADERS).json()] == [
        costco_row["id"],
        walmart_row["id"],
    ]

    edited = client.patch(
        PATH + "/" + walmart_row["id"],
        headers=HEADERS,
        json={"name": "Walmart Supercentre", "website_url": None},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Walmart Supercentre"
    assert edited.json()["website_url"] is None

    reordered = client.put(
        PATH + "/order",
        headers=HEADERS,
        json={"store_ids": [walmart_row["id"], costco_row["id"]]},
    )
    assert reordered.status_code == 200, reordered.text
    assert [row["id"] for row in reordered.json()] == [
        walmart_row["id"],
        costco_row["id"],
    ]
    assert [row["sort_order"] for row in reordered.json()] == [0, 1]

    identity["id"] = OWNER
    assert client.delete(PATH + "/" + costco_row["id"], headers=HEADERS).status_code == 204
    assert [row["id"] for row in client.get(PATH, headers=HEADERS).json()] == [
        walmart_row["id"]
    ]
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM household_stores")).scalar() == 1


def test_household_isolation_and_stale_reorder_rejected(stores_api):
    client, identity, _ = stores_api
    own = client.post(PATH, headers=HEADERS, json={"name": "Costco"}).json()

    identity["id"] = OUTSIDER
    assert client.get(PATH, headers=HEADERS).status_code == 403
    other_headers = {"X-Household-ID": OTHER}
    foreign = client.post(PATH, headers=other_headers, json={"name": "No Frills"})
    assert foreign.status_code == 201, foreign.text
    assert [row["name"] for row in client.get(PATH, headers=other_headers).json()] == ["No Frills"]
    assert client.patch(
        PATH + "/" + own["id"],
        headers=other_headers,
        json={"name": "Blocked"},
    ).status_code == 404
    assert client.delete(PATH + "/" + own["id"], headers=other_headers).status_code == 404

    identity["id"] = OWNER
    assert [row["name"] for row in client.get(PATH, headers=HEADERS).json()] == ["Costco"]
    response = client.put(
        PATH + "/order",
        headers=HEADERS,
        json={"store_ids": [own["id"], foreign.json()["id"]]},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "  "},
        {"name": "x", "website_url": "not-a-url"},
        {"name": "x", "website_url": "ftp://example.com"},
        {"name": "x", "household_id": OTHER},
    ],
)
def test_invalid_create(stores_api, body):
    assert stores_api[0].post(PATH, headers=HEADERS, json=body).status_code == 422


def test_invalid_update_reorder_and_authentication(stores_api):
    client, _, _ = stores_api
    store = client.post(PATH, headers=HEADERS, json={"name": "Costco"}).json()
    url = PATH + "/" + store["id"]

    for body in [{}, {"name": None}, {"name": ""}, {"website_url": "javascript:alert(1)"}]:
        assert client.patch(url, headers=HEADERS, json=body).status_code == 422

    assert client.put(PATH + "/order", headers=HEADERS, json={"store_ids": []}).status_code == 422
    assert client.put(
        PATH + "/order",
        headers=HEADERS,
        json={"store_ids": [store["id"], store["id"]]},
    ).status_code == 422

    assert client.get(PATH).status_code == 400
    app.dependency_overrides.pop(get_current_user)
    for method, path, payload in [
        ("get", PATH, None),
        ("post", PATH, {"name": "x"}),
        ("patch", url, {"name": "y"}),
        ("delete", url, None),
        ("put", PATH + "/order", {"store_ids": [store["id"]]}),
    ]:
        assert client.request(method, path, headers=HEADERS, json=payload).status_code == 401
