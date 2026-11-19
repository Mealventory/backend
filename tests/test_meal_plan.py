"""API-level two-member synchronization, stale revisions, isolation and import replay."""
import pytest

from app.models.household import Household
from app.models.meal_plan import MealPlanImport, MealPlanSlot
from tests.test_household_inventory import OWNER, MEMBER, OUTSIDER, HOME, OTHER, inventory_api

PATH = "/api/v1/meal-plan"
HEADERS = {"X-Household-ID": HOME}
RECIPE = {
    "id": "recipe-1", "name": "Soup", "time": "25 min", "difficulty": "Easy",
    "match": 80, "uses": ["Carrot"], "emoji": "🍲", "tag": "Dinner",
    "description": "Warm soup", "steps": ["Cook carrots"],
}
OTHER_RECIPE = {**RECIPE, "id": "recipe-2", "name": "Salad"}
DATE = "2026-11-23"


@pytest.fixture
def meal_api(inventory_api):
    client, identity, engine = inventory_api
    Household.__table__.create(engine)
    MealPlanSlot.__table__.create(engine)
    MealPlanImport.__table__.create(engine)
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        db.add_all([
            Household(id=HOME, name="Kitchen", created_by=OWNER),
            Household(id=OTHER, name="Another kitchen", created_by=OUTSIDER),
        ])
        db.commit()
    return client, identity


def _assign(client, day=DATE, slot="dinner", recipe=RECIPE, revision=0):
    return client.put(PATH + "/slots", headers=HEADERS, json={
        "date": day, "slot": slot, "recipe": recipe, "expected_revision": revision,
    })


def test_two_members_refresh_and_stale_edits(meal_api):
    client, identity = meal_api
    created = _assign(client)
    assert created.status_code == 200, created.text
    assert created.json()["slot_versions"][DATE + ":dinner"] == 1

    identity["id"] = MEMBER
    viewed = client.get(PATH, headers=HEADERS)
    assert viewed.status_code == 200
    assert viewed.json()["meals"][0]["recipe"]["name"] == "Soup"

    updated = _assign(client, recipe=OTHER_RECIPE, revision=1)
    assert updated.status_code == 200, updated.text
    assert updated.json()["slot_versions"][DATE + ":dinner"] == 2

    identity["id"] = OWNER
    conflict = _assign(client, revision=1)
    assert conflict.status_code == 409
    assert client.get(PATH, headers=HEADERS).json()["meals"][0]["recipe"]["name"] == "Salad"

    identity["id"] = OUTSIDER
    assert client.get(PATH, headers=HEADERS).status_code == 403
    assert _assign(client, revision=2).status_code == 403
    assert client.post(PATH + "/move", headers=HEADERS, json={
        "source_date": DATE, "source_slot": "dinner", "source_revision": 2,
        "target_date": DATE, "target_slot": "lunch", "target_revision": 0,
    }).status_code == 403
    assert client.get(PATH, headers={"X-Household-ID": OTHER}).json()["meals"] == []


def test_move_swaps_atomically_and_tombstone_rejects_old_edits(meal_api):
    client, identity = meal_api
    assert _assign(client).status_code == 200
    assert _assign(client, slot="lunch", recipe=OTHER_RECIPE).status_code == 200

    move = client.post(PATH + "/move", headers=HEADERS, json={
        "source_date": DATE, "source_slot": "dinner", "source_revision": 1,
        "target_date": DATE, "target_slot": "lunch", "target_revision": 1,
    })
    assert move.status_code == 200, move.text
    state = move.json()
    assert {(meal["slot"], meal["recipe"]["name"]) for meal in state["meals"]} == {
        ("dinner", "Salad"), ("lunch", "Soup"),
    }

    identity["id"] = MEMBER
    stale = client.post(PATH + "/move", headers=HEADERS, json={
        "source_date": DATE, "source_slot": "lunch", "source_revision": 1,
        "target_date": DATE, "target_slot": "dinner", "target_revision": 1,
    })
    assert stale.status_code == 409
    assert len(client.get(PATH, headers=HEADERS).json()["meals"]) == 2

    deleted = client.post(PATH + "/slots/remove", headers=HEADERS, json={
        "date": DATE, "slot": "lunch", "expected_revision": 2,
    })
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["slot_versions"][DATE + ":lunch"] == 3
    assert _assign(client, slot="lunch", revision=0).status_code == 409
    assert _assign(client, slot="lunch", revision=3).status_code == 200


def test_reviewed_import_never_overwrites_and_replays_once(meal_api):
    client, identity = meal_api
    assert _assign(client).status_code == 200
    payload = {
        "import_key": "local-v1",
        "meals": [
            {"date": DATE, "slot": "dinner", "recipe": OTHER_RECIPE,
             "expected_revision": 1},
            {"date": DATE, "slot": "lunch", "recipe": RECIPE,
             "expected_revision": 0},
        ],
    }
    preview = client.post(PATH + "/import/preview", headers=HEADERS, json=payload)
    assert preview.status_code == 200, preview.text
    candidates = preview.json()["candidates"]
    assert [item["status"] for item in candidates] == ["occupied", "available"]
    assert client.post(PATH + "/import", headers=HEADERS, json=payload).status_code == 409

    reviewed = {**payload, "meals": [payload["meals"][1]]}
    imported = client.post(PATH + "/import", headers=HEADERS, json=reviewed)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_local_plan"] is True
    assert len(imported.json()["meals"]) == 2
    replay = client.post(PATH + "/import", headers=HEADERS, json=reviewed)
    assert replay.status_code == 200 and len(replay.json()["meals"]) == 2
    assert replay.json()["slot_versions"][DATE + ":lunch"] == 1

    changed = {**reviewed, "meals": [{**reviewed["meals"][0], "recipe": OTHER_RECIPE}]}
    assert client.post(PATH + "/import", headers=HEADERS, json=changed).status_code == 409

    identity["id"] = MEMBER
    assert client.get(PATH, headers=HEADERS).json()["imported_local_plan"] is False
    assert client.post(PATH + "/import", headers=HEADERS, json=reviewed).status_code == 409


@pytest.mark.parametrize("bad_date", ["2026-02-30", "2027-02-29", "2026-13-01"])
def test_impossible_dates_rejected(meal_api, bad_date):
    assert _assign(meal_api[0], day=bad_date).status_code == 422


def test_auth_and_preconditions_required(meal_api):
    client, identity = meal_api
    assert client.get(PATH).status_code == 400
    assert client.put(PATH + "/slots", headers=HEADERS, json={
        "date": DATE, "slot": "dinner", "recipe": RECIPE,
    }).status_code == 422
    identity["id"] = OUTSIDER
    assert client.post(PATH + "/import/preview", headers=HEADERS, json={
        "import_key": "local-v1",
        "meals": [{"date": DATE, "slot": "dinner", "recipe": RECIPE, "expected_revision": 0}],
    }).status_code == 403
