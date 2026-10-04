"""Generate suggestions from active, non-expired household inventory."""

from datetime import date
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.schemas.recipe_suggestion import (
    RecipeProviderResponse,
    RecipeSuggestionsResponse,
)
from app.services.household_inventory_service import list_items
from app.services.recipe_ai_service import (
    RecipeProviderTimeout,
    RecipeProviderUnavailable,
    generate_recipe_suggestions,
)


def partition_inventory(rows, today=None):
    today = today or date.today()
    by_name = {}
    for row in rows:
        if row["status"] != "active" or float(row["quantity"]) <= 0:
            continue
        expiry = row["expiry_date"]
        if isinstance(expiry, str):
            expiry = date.fromisoformat(expiry)
        days = (expiry - today).days if expiry else None
        if days is not None and days < 0:
            continue
        name = row["name"].strip()
        key = name.casefold()
        old = by_name.get(key)
        if old is None or (
            days is not None
            and (old["days_until_expiry"] is None or days < old["days_until_expiry"])
        ):
            by_name[key] = {"name": name, "days_until_expiry": days}

    priority = sorted(
        [
            item
            for item in by_name.values()
            if item["days_until_expiry"] is not None
            and item["days_until_expiry"] <= 3
        ],
        key=lambda item: item["days_until_expiry"],
    )
    other = [
        item
        for item in by_name.values()
        if item["days_until_expiry"] is None or item["days_until_expiry"] > 3
    ]
    return priority, other


async def get_inventory_recipes(household_id: UUID, db):
    priority, other = partition_inventory(list_items(db, household_id))
    if not priority and not other:
        return RecipeSuggestionsResponse().model_dump()

    try:
        result = RecipeProviderResponse.model_validate(
            await generate_recipe_suggestions(priority, other)
        )
        available = {item["name"].casefold(): item["name"] for item in priority + other}
        urgent = {item["name"].casefold() for item in priority}
        recipes = []

        for recipe in result.recipes:
            names = list(
                dict.fromkeys(
                    name.strip().casefold()
                    for name in (
                        recipe.uses_priority_items
                        + recipe.uses_other_items
                        + recipe.optional_pantry_basics
                    )
                    if name.strip()
                )
            )
            recipe.uses_priority_items = [available[name] for name in names if name in urgent]
            recipe.uses_other_items = [
                available[name]
                for name in names
                if name in available and name not in urgent
            ]
            recipe.optional_pantry_basics = [
                name for name in names if name not in available
            ]

            if not recipe.uses_priority_items and not recipe.uses_other_items:
                continue
            if priority and not recipe.uses_priority_items:
                continue
            recipes.append(recipe)

        if not recipes:
            raise ValueError("No grounded recipes")

        return RecipeSuggestionsResponse(
            recipes=recipes,
            priority_items=priority,
        ).model_dump()
    except (RecipeProviderTimeout, httpx.TimeoutException) as exc:
        raise HTTPException(
            504,
            "Recipe generation timed out. Please try again.",
        ) from exc
    except (
        RecipeProviderUnavailable,
        httpx.HTTPError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
    ) as exc:
        raise HTTPException(
            503,
            "Recipe suggestions are unavailable. Please try again shortly.",
        ) from exc
