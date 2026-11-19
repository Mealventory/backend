"""Real PostgreSQL two-session regression tests for shared meal-plan concurrency.

This suite uses only the disposable Docker database fixture, never live Supabase.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.meal_plan import MealPlanImport, MealPlanSlot
from app.schemas.meal_plan import MealPlanAssign, MealPlanMove, MealPlanRemove
from app.schemas.saved_recipe import RecipeSnapshot
from app.services import household_service, meal_plan_service
from tests.test_household_postgres import postgres_engine, A, B
from tests.test_init_db_postgres import pytestmark

MONDAY = date(2026, 11, 23)
RECIPE = RecipeSnapshot(
    id="soup-1", name="Soup", time="20 min", difficulty="Easy", match=90,
    uses=["Carrot"], emoji="🍲", tag="Lunch", description="Soup", steps=["Cook"],
)
SALAD = RECIPE.model_copy(update={"id": "salad-1", "name": "Salad"})


@pytest.fixture
def pg_meal_plan(postgres_engine):
    MealPlanSlot.__table__.create(postgres_engine, checkfirst=True)
    MealPlanImport.__table__.create(postgres_engine, checkfirst=True)
    return postgres_engine


def test_two_members_share_meals_and_swap_atomically(pg_meal_plan):
    with Session(pg_meal_plan) as db:
        home = household_service.create_household(db, A, "Shared planner")
        household_service.join_household(db, B, home.invite_code)
        meal_plan_service.assign(db, home.id, A, MealPlanAssign(
            date=MONDAY, slot="lunch", recipe=RECIPE, expected_revision=0,
        ))
        meal_plan_service.assign(db, home.id, A, MealPlanAssign(
            date=MONDAY, slot="dinner", recipe=SALAD, expected_revision=0,
        ))

    # Different member, new PostgreSQL session: no device-local state.
    with Session(pg_meal_plan) as db:
        before = meal_plan_service.list_plan(db, home.id, B)
        assert {(row["slot"], row["recipe"]["name"]) for row in before["meals"]} == {
            ("lunch", "Soup"), ("dinner", "Salad"),
        }
        result = meal_plan_service.move(db, home.id, B, MealPlanMove(
            source_date=MONDAY, source_slot="lunch", source_revision=1,
            target_date=MONDAY, target_slot="dinner", target_revision=1,
        ))
        assert result["slot_versions"][f"{MONDAY}:lunch"] == 2
        assert result["slot_versions"][f"{MONDAY}:dinner"] == 2

    with Session(pg_meal_plan) as db:
        after = meal_plan_service.list_plan(db, home.id, A)
        assert {(row["slot"], row["recipe"]["name"]) for row in after["meals"]} == {
            ("lunch", "Salad"), ("dinner", "Soup"),
        }


def test_concurrent_stale_schedule_rejected_and_tombstone_persists(pg_meal_plan):
    with Session(pg_meal_plan) as db:
        home = household_service.create_household(db, A, "Concurrent planner")
        household_service.join_household(db, B, home.invite_code)

    barrier = Barrier(2)
    def save(user_recipe):
        user, recipe = user_recipe
        with Session(pg_meal_plan) as db:
            barrier.wait(timeout=10)
            try:
                result = meal_plan_service.assign(db, home.id, user, MealPlanAssign(
                    date=MONDAY, slot="dinner", recipe=recipe, expected_revision=0,
                ))
                return ("saved", result["slot_versions"][f"{MONDAY}:dinner"])
            except HTTPException as exc:
                return ("conflict", exc.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [(A, RECIPE), (B, SALAD)]))
    assert sorted(results) == [("conflict", 409), ("saved", 1)]

    with Session(pg_meal_plan) as db:
        one = meal_plan_service.list_plan(db, home.id, A)
        assert len(one["meals"]) == 1
        assert one["slot_versions"][f"{MONDAY}:dinner"] == 1
        meal_plan_service.remove(db, home.id, B, MealPlanRemove(
            date=MONDAY, slot="dinner", expected_revision=1,
        ))

    with Session(pg_meal_plan) as db:
        state = meal_plan_service.list_plan(db, home.id, A)
        assert state["meals"] == []
        assert state["slot_versions"][f"{MONDAY}:dinner"] == 2
        with pytest.raises(HTTPException) as exc:
            meal_plan_service.assign(db, home.id, A, MealPlanAssign(
                date=MONDAY, slot="dinner", recipe=RECIPE, expected_revision=0,
            ))
        assert exc.value.status_code == 409
