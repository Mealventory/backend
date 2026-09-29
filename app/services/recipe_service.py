"""Generate suggestions from active, non-expired household inventory."""
from datetime import date
from uuid import UUID
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from app.services.recipe_ai_service import generate_recipe_suggestions
from app.services.household_inventory_service import list_items

class Suggestion(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    uses_priority_items: list[str]
    uses_other_items: list[str]
    optional_pantry_basics: list[str]
    prep_time_minutes: int = Field(ge=0, le=1440)
    cook_time_minutes: int = Field(ge=0, le=1440)
    difficulty: Literal['Easy', 'Medium', 'Hard']
    steps: list[str] = Field(min_length=1, max_length=30)
    waste_reduction_reason: str

class Suggestions(BaseModel):
    recipes: list[Suggestion] = Field(min_length=1, max_length=5)

def partition_inventory(rows, today=None):
    today = today or date.today()
    by_name = {}
    for row in rows:
        if row['status'] != 'active' or float(row['quantity']) <= 0:
            continue
        expiry = row['expiry_date']
        if isinstance(expiry, str):
            expiry = date.fromisoformat(expiry)
        days = (expiry - today).days if expiry else None
        if days is not None and days < 0:
            continue
        name = row['name'].strip()
        key = name.casefold()
        old = by_name.get(key)
        if old is None or (days is not None and (old['days_until_expiry'] is None or days < old['days_until_expiry'])):
            by_name[key] = {'name': name, 'days_until_expiry': days}
    priority = sorted([i for i in by_name.values() if i['days_until_expiry'] is not None and i['days_until_expiry'] <= 3], key=lambda i: i['days_until_expiry'])
    other = [i for i in by_name.values() if i['days_until_expiry'] is None or i['days_until_expiry'] > 3]
    return priority, other

async def get_inventory_recipes(household_id: UUID, db):
    priority, other = partition_inventory(list_items(db, household_id))
    if not priority and not other:
        return {'recipes': [], 'priority_items': []}
    try:
        result = Suggestions.model_validate(await generate_recipe_suggestions(priority, other))
        available = {i['name'].casefold(): i['name'] for i in priority + other}
        urgent = {i['name'].casefold() for i in priority}
        recipes = []
        for recipe in result.recipes:
            names = list(dict.fromkeys(n.strip().casefold() for n in recipe.uses_priority_items + recipe.uses_other_items + recipe.optional_pantry_basics if n.strip()))
            recipe.uses_priority_items = [available[n] for n in names if n in urgent]
            recipe.uses_other_items = [available[n] for n in names if n in available and n not in urgent]
            recipe.optional_pantry_basics = [n for n in names if n not in available]
            if not recipe.uses_priority_items and not recipe.uses_other_items:
                continue
            if priority and not recipe.uses_priority_items:
                continue
            recipes.append(recipe.model_dump())
        if not recipes:
            raise ValueError('No grounded recipes')
        return {'recipes': recipes, 'priority_items': priority}
    except httpx.TimeoutException as exc:
        raise HTTPException(504, 'Recipe generation timed out. Please try again.') from exc
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise HTTPException(503, 'Recipe suggestions are unavailable. Please try again shortly.') from exc
