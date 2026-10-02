"""Opt-in concurrency coverage using disposable PostgreSQL, never the app database."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services import household_service, household_inventory_service as inventory
from app.services.recipe_completion_service import complete_recipe
from app.schemas.household_inventory import ItemCreate
from app.schemas.recipe_completion import RecipeCompletion
from app.core.auth_errors import AuthProblem
from tests.test_household_postgres import postgres_engine, A
from tests.test_init_db_postgres import pytestmark


def test_concurrent_retries_and_competing_meals(postgres_engine):
    migration = Path(__file__).resolve().parents[1] / 'scripts/add_recipe_completions.sql'
    with postgres_engine.begin() as connection:
        for role in ('anon', 'authenticated'):
            connection.exec_driver_sql(f"DO $$ BEGIN CREATE ROLE {role}; EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
        connection.exec_driver_sql(migration.read_text())
        connection.exec_driver_sql(migration.read_text())
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Meal concurrency')
        row = inventory.add_item(db, home.id, ItemCreate(name='Rice', quantity=5, unit='cups'))
    request = dict(completion_id='concurrent-meal-12345', recipe_id='rice-bowl', recipe_name='Rice bowl',
                   items=[dict(item_id=row['id'], quantity='2', expected_quantity='5', unit='cups')])
    barrier = Barrier(2)
    def finish(payload):
        with Session(postgres_engine) as db:
            barrier.wait(timeout=10)
            try:
                return complete_recipe(db, home.id, RecipeCompletion(**payload))
            except AuthProblem as error:
                return error.status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(finish, [request, request]))
    assert results[0] == results[1]
    with Session(postgres_engine) as db:
        assert inventory.get_item(db, home.id, row['id'])['quantity'] == 3
    request['items'][0]['expected_quantity'] = '3'
    first = dict(request, completion_id='next-meal-first-12345')
    second = dict(request, completion_id='next-meal-second-12345')
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(finish, [first, second]))
    assert results.count(409) == 1
    with Session(postgres_engine) as db:
        assert inventory.get_item(db, home.id, row['id'])['quantity'] == 1
        assert db.execute(text('SELECT count(*) FROM household_recipe_completions')).scalar() == 2
