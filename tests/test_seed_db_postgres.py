from datetime import date, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.scripts.seed_db import seed
from app.db.fixtures.demo import fixture_id, USERS
from app.services.household_service import join_household
from tests.test_household_postgres import postgres_engine
from tests.test_init_db_postgres import pytestmark


def test_seed_repeat_reset_and_enrollment(postgres_engine):
    today = date.today()
    with postgres_engine.begin() as db:
        seed(db, today=today)
    with postgres_engine.begin() as db:
        assert db.execute(text('SELECT count(*) FROM households')).scalar() == 2
        assert db.execute(text('SELECT count(DISTINCT user_id) FROM household_members')).scalar() == 4
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 50
        assert db.execute(text('SELECT count(*) FROM recipes')).scalar() == 10
        assert db.execute(text('SELECT count(*) FROM recipe_ingredients')).scalar() == 30
        assert db.execute(text('SELECT count(DISTINCT zone) FROM storage_locations')).scalar() == 4
        assert db.execute(text("SELECT count(*) FROM inventory_items WHERE status='active' AND expiry_date BETWEEN :today AND :soon"),
                          {'today': today, 'soon': today + timedelta(days=3)}).scalar() >= 5
        original = db.execute(text('SELECT id, expiry_date, updated_at FROM inventory_items ORDER BY id')).all()
        seed(db, today=today + timedelta(days=1))
        assert db.execute(text('SELECT id, expiry_date, updated_at FROM inventory_items ORDER BY id')).all() == original
        unrelated = str(uuid4())
        db.execute(text("INSERT INTO inventory_items(id,household_id,food_id,quantity,unit) VALUES (:id,:home,:food,8,'units')"),
                   {'id': unrelated, 'home': fixture_id('home:0'), 'food': fixture_id('food:0')})
        seed(db, reset=True, items=60, today=today + timedelta(days=1))
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 61
        assert db.execute(text('SELECT quantity FROM inventory_items WHERE id=:id'), {'id': unrelated}).scalar() == 8
        seed(db, reset=True, items=50)
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 51
    with Session(postgres_engine) as session:
        result = join_household(session, str(uuid4()), 'DEMO01')
        assert str(result.id) == fixture_id('home:0') and result.role == 'member'


def test_failure_rolls_back_every_write(postgres_engine, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from app.scripts import seed_db
    with postgres_engine.begin() as db:
        seed(db)
    with postgres_engine.begin() as db:
        before = db.execute(text('SELECT count(*) FROM inventory_items')).scalar()
    with pytest.raises(ValueError):
        with postgres_engine.begin() as db:
            seed(db, reset=True, user_ids=[str(uuid4()) for _ in range(4)])
    with postgres_engine.begin() as db:
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == before

    # Fail after inventory reset has already executed; the transaction restores it.
    monkeypatch.setattr(seed_db, 'RECIPES', [('', [0, 1])])
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as db:
            seed(db, reset=True, items=75)
    with postgres_engine.begin() as db:
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == before
