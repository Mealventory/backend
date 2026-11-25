"""CSV portability remains tenant scoped and preview is read-only."""
from sqlalchemy import text

from tests.test_household_inventory import HOME, OTHER, OUTSIDER, inventory_api


HEADER = "schema_version,food_name,category,quantity,unit,storage_zone,expiry_date\n"


def _preview(client, csv_text, household=HOME):
    return client.post(
        "/api/v1/items/import/preview",
        headers={"X-Household-ID": household},
        files={"file": ("pantry.csv", csv_text.encode("utf-8"), "text/csv")},
    )


def _confirm(client, preview, choices, key="pantry-import-123456789"):
    return client.post(
        "/api/v1/items/import/confirm",
        headers={"X-Household-ID": HOME, "Idempotency-Key": key},
        json={"operation_id": preview["operation_id"], "choices": choices},
    )


def test_export_preview_confirm_and_retry_are_safe(inventory_api):
    client, _, engine = inventory_api
    headers = {"X-Household-ID": HOME}
    assert client.post("/api/v1/items", headers=headers, json={
        "name": "=2+2", "category": "Pantry", "quantity": "1.250", "unit": "kg",
        "storage_zone": "fridge", "expiry_date": "2027-02-03",
        "image_ref": f"{HOME}/private.jpg",
    }).status_code == 201
    exported = client.get("/api/v1/items/export.csv", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "'=2+2" in exported.text
    assert "private.jpg" not in exported.text
    round_trip = _preview(client, exported.text)
    assert round_trip.status_code == 200, round_trip.text
    assert round_trip.json()["rows"][0]["status"] == "exact_duplicate"
    with engine.connect() as db:
        count_before = db.execute(text("SELECT count(*) FROM inventory_items")).scalar_one()
    preview = _preview(client, HEADER + "1,Oats,Pantry,2.5,kg,pantry,2027-03-01\n")
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"][0]["status"] == "ready"
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM inventory_items")).scalar_one() == count_before
    choices = [{"row": 2, "action": "add"}]
    first = _confirm(client, preview.json(), choices)
    again = _confirm(client, preview.json(), choices)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM inventory_items")).scalar_one() == count_before + 1


def test_preview_reports_invalid_and_existing_duplicate_rows(inventory_api):
    client, _, _ = inventory_api
    headers = {"X-Household-ID": HOME}
    assert client.post("/api/v1/items", headers=headers, json={"name": "Rice"}).status_code == 201
    preview = _preview(client, HEADER + "1,Rice,Pantry,1,units,pantry,\n1,Flour,Pantry,nope,kg,pantry,\n")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["rows"][0]["status"] == "exact_duplicate"
    assert body["errors"][0]["row"] == 3
    confirmed = _confirm(client, body, [{"row": 2, "action": "skip"}])
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["results"][0]["action"] == "skip"


def test_preview_accepts_unicode_food_names(inventory_api):
    client, _, _ = inventory_api
    preview = _preview(client, HEADER + "1,Crème 雪 peas,Produce,0.125,kg,freezer,2027-04-05\n")
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"][0]["item"]["name"] == "Crème 雪 peas"
    assert preview.json()["rows"][0]["item"]["quantity"] == "0.125"


def test_preview_marks_duplicates_within_the_uploaded_file(inventory_api):
    client, _, _ = inventory_api
    preview = _preview(client, HEADER +
                       "1,Oats,Pantry,1,units,pantry,\n"
                       "1,Oats,Pantry,1,units,pantry,\n")
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"][1]["status"] == "duplicate_in_file"
    assert preview.json()["rows"][1]["duplicate_of_row"] == 2


def test_preview_rejects_foreign_household_and_oversized_csv(inventory_api):
    client, identity, _ = inventory_api
    identity["id"] = OUTSIDER
    denied = _preview(client, HEADER + "1,Oats,Pantry,1,units,pantry,\n")
    assert denied.status_code == 403
    oversized = _preview(client, "x" * (1_048_577), household=OTHER)
    assert oversized.status_code == 413


def test_signed_preview_cannot_be_confirmed_for_another_household(inventory_api):
    client, identity, _ = inventory_api
    preview = _preview(client, HEADER + "1,Oats,Pantry,1,units,pantry,\n").json()
    identity["id"] = OUTSIDER
    response = client.post(
        "/api/v1/items/import/confirm",
        headers={"X-Household-ID": OTHER, "Idempotency-Key": "pantry-import-123456789"},
        json={"operation_id": preview["operation_id"], "choices": [{"row": 2, "action": "add"}]},
    )
    assert response.status_code == 403


def test_confirm_key_cannot_be_reused_for_another_review(inventory_api):
    client, _, _ = inventory_api
    one = _preview(client, HEADER + "1,Oats,Pantry,1,units,pantry,\n").json()
    two = _preview(client, HEADER + "1,Beans,Pantry,1,units,pantry,\n").json()
    first = _confirm(client, one, [{"row": 2, "action": "add"}])
    changed = _confirm(client, two, [{"row": 2, "action": "add"}])
    assert first.status_code == 200
    assert changed.status_code == 409
