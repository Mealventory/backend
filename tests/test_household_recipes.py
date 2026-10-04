import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import recipe_service as service
from tests.test_household_inventory import (
    HOME,
    MEMBER,
    OTHER,
    OUTSIDER,
    OWNER,
    inventory_api,
)


def row(name, days, status="active", quantity=1):
    return dict(
        name=name,
        expiry_date=None
        if days is None
        else date(2026, 9, 29) + timedelta(days=days),
        status=status,
        quantity=quantity,
    )


def test_actual_expiry_boundaries_and_duplicates():
    priority, other = service.partition_inventory(
        [
            row("Milk", 3),
            row("milk", 0),
            row("Rice", None),
            row("Eggs", 4),
            row("Old", -1),
            row("Gone", 1, "consumed"),
            row("Zero", 1, quantity=0),
        ],
        date(2026, 9, 29),
    )
    assert priority == [{"name": "milk", "days_until_expiry": 0}]
    assert [item["name"] for item in other] == ["Rice", "Eggs"]


RECIPE = dict(
    title="Milk porridge",
    uses_priority_items=["Milk"],
    uses_other_items=[],
    optional_pantry_basics=["salt"],
    prep_time_minutes=5,
    cook_time_minutes=10,
    difficulty="Easy",
    steps=["Warm Milk with salt."],
    waste_reduction_reason="Use Milk first.",
)


def test_household_scope_member_access_and_real_dates(inventory_api, monkeypatch):
    client, identity, _ = inventory_api
    for home, user, name in [
        (HOME, OWNER, "Milk"),
        (OTHER, OUTSIDER, "Secret food"),
    ]:
        identity["id"] = user
        assert (
            client.post(
                "/api/v1/items",
                headers={"X-Household-ID": home},
                json={
                    "name": name,
                    "quantity": 1,
                    "unit": "units",
                    "expiry_date": str(date.today() + timedelta(days=3)),
                },
            ).status_code
            == 201
        )

    identity["id"] = MEMBER
    generator = AsyncMock(return_value={"recipes": [RECIPE]})
    monkeypatch.setattr(service, "generate_recipe_suggestions", generator)

    response = client.get("/api/v1/recipes/", headers={"X-Household-ID": HOME})
    assert response.status_code == 200, response.text
    generator.assert_awaited_once_with(
        [{"name": "Milk", "days_until_expiry": 3}],
        [],
    )
    assert response.json()["recipes"][0]["optional_pantry_basics"] == ["salt"]
    assert (
        client.get(
            "/api/v1/recipes/",
            headers={"X-Household-ID": OTHER},
        ).status_code
        == 403
    )
    assert generator.await_count == 1


def test_empty_inventory_does_not_call_provider(inventory_api, monkeypatch):
    client, _, _ = inventory_api
    generator = AsyncMock()
    monkeypatch.setattr(service, "generate_recipe_suggestions", generator)

    assert client.get(
        "/api/v1/recipes/",
        headers={"X-Household-ID": HOME},
    ).json() == {"recipes": [], "priority_items": []}
    generator.assert_not_awaited()


@pytest.mark.parametrize(
    "failure,status,detail",
    [
        (
            ValueError("bad output"),
            503,
            "Recipe suggestions are unavailable. Please try again shortly.",
        ),
        (
            httpx.ReadTimeout("slow"),
            504,
            "Recipe generation timed out. Please try again.",
        ),
    ],
)
def test_provider_failures_are_actionable(monkeypatch, failure, status, detail):
    monkeypatch.setattr(service, "list_items", lambda *args: [row("Milk", None)])
    monkeypatch.setattr(
        service,
        "generate_recipe_suggestions",
        AsyncMock(side_effect=failure),
    )

    with pytest.raises(service.HTTPException) as err:
        asyncio.run(service.get_inventory_recipes(HOME, None))

    assert err.value.status_code == status
    assert err.value.detail == detail
    assert "bad output" not in err.value.detail
    assert "slow" not in err.value.detail


def test_hallucinated_stock_is_reclassified_as_missing(monkeypatch):
    monkeypatch.setattr(service, "list_items", lambda *args: [row("Milk", None)])
    monkeypatch.setattr(
        service,
        "generate_recipe_suggestions",
        AsyncMock(
            return_value={
                "recipes": [{**RECIPE, "uses_other_items": ["Carrot"]}]
            }
        ),
    )

    result = asyncio.run(service.get_inventory_recipes(HOME, None))["recipes"][0]
    assert result["uses_priority_items"] == []
    assert result["uses_other_items"] == ["Milk"]
    assert result["optional_pantry_basics"] == ["carrot", "salt"]


def test_recipe_openapi_response_is_typed(inventory_api):
    client, _, _ = inventory_api
    schema = client.get("/openapi.json").json()

    response_schema = (
        schema["paths"]["/api/v1/recipes/"]["get"]["responses"]["200"]["content"]
        ["application/json"]["schema"]
    )
    assert response_schema == {
        "$ref": "#/components/schemas/RecipeSuggestionsResponse"
    }
    assert "RecipeSuggestion" in schema["components"]["schemas"]
    assert "RecipeInventoryItem" in schema["components"]["schemas"]
