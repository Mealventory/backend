import asyncio
import json

import httpx
import pytest

from app.schemas.recipe_suggestion import RecipeProviderResponse
from app.services import recipe_ai_service as provider


RECIPE = {
    "title": "Milk porridge",
    "uses_priority_items": ["Milk"],
    "uses_other_items": [],
    "optional_pantry_basics": ["salt"],
    "prep_time_minutes": 5,
    "cook_time_minutes": 10,
    "difficulty": "Easy",
    "steps": ["Warm Milk with salt."],
    "waste_reduction_reason": "Use Milk first.",
}


def install_transport(monkeypatch, handler):
    factory = httpx.AsyncClient
    monkeypatch.setattr(
        provider.httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_openrouter_is_the_explicit_recipe_provider(monkeypatch):
    monkeypatch.setattr(provider, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(provider, "OPENROUTER_MODEL", "test/model")

    def handler(request):
        assert str(request.url) == provider.OPENROUTER_URL
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test/model"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"recipes": [RECIPE]})
                        }
                    }
                ]
            },
        )

    install_transport(monkeypatch, handler)
    result = asyncio.run(
        provider.generate_recipe_suggestions(
            [{"name": "Milk", "days_until_expiry": 1}],
            [],
        )
    )

    assert isinstance(result, RecipeProviderResponse)
    assert result.recipes[0].title == "Milk porridge"


def test_provider_outage_is_wrapped_without_leaking_response(monkeypatch):
    monkeypatch.setattr(provider, "OPENROUTER_API_KEY", "test-key")

    def handler(request):
        return httpx.Response(503, json={"error": "provider internals"}, request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(provider.RecipeProviderUnavailable) as err:
        asyncio.run(
            provider.generate_recipe_suggestions(
                [{"name": "Milk", "days_until_expiry": None}],
                [],
            )
        )
    assert "provider internals" not in str(err.value)


def test_provider_timeout_has_distinct_error(monkeypatch):
    monkeypatch.setattr(provider, "OPENROUTER_API_KEY", "test-key")

    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(provider.RecipeProviderTimeout):
        asyncio.run(
            provider.generate_recipe_suggestions(
                [{"name": "Milk", "days_until_expiry": None}],
                [],
            )
        )


def test_invalid_provider_payload_is_rejected(monkeypatch):
    monkeypatch.setattr(provider, "OPENROUTER_API_KEY", "test-key")

    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"recipes":[]}'}}]},
            request=request,
        )

    install_transport(monkeypatch, handler)
    with pytest.raises(provider.RecipeProviderUnavailable):
        asyncio.run(
            provider.generate_recipe_suggestions(
                [{"name": "Milk", "days_until_expiry": None}],
                [],
            )
        )
