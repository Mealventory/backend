"""Opt-in persistence check against the actual DDL in disposable PostgreSQL 16."""
from sqlalchemy.orm import Session
from app.services import household_service
from app.services import household_inventory_service as inventory
from app.schemas.household_inventory import ItemCreate, ItemOut, ItemUpdate
from tests.test_household_postgres import postgres_engine, A
from tests.test_init_db_postgres import pytestmark


def test_inventory_commit_visible_between_sessions(postgres_engine):
    with Session(postgres_engine) as owner:
        home = household_service.create_household(owner, A, 'Inventory test')
        created = inventory.add_item(owner, home.id, ItemCreate(name='Rice', quantity='2.5', unit='kg'))
        ItemOut.model_validate(created)
    with Session(postgres_engine) as phone:
        assert len(inventory.list_items(phone, home.id)) == 1
        inventory.delete_item(phone, home.id, created['id'])
    with Session(postgres_engine) as other_phone:
        assert inventory.list_items(other_phone, home.id) == []


def test_edit_and_status_trigger_postgres(postgres_engine):
    from sqlalchemy import text
    from concurrent.futures import ThreadPoolExecutor
    from app.core.auth_errors import AuthProblem
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Transitions')
        rows = inventory.add_batch(db, home.id, [ItemCreate(name=f'Food {i}') for i in range(6)])
        assert len(rows) == 6
        item_id = rows[0]['id']
        before = db.execute(text('SELECT updated_at FROM inventory_items WHERE id=:id'), {'id': item_id}).scalar()
        row = inventory.update_item(db, home.id, item_id, ItemUpdate(quantity='2.125', expiry_date=None))
        assert str(row['quantity']) == '2.125'
        after = db.execute(text('SELECT updated_at FROM inventory_items WHERE id=:id'), {'id': item_id}).scalar()
        assert after > before
    def change(target):
        with Session(postgres_engine) as db:
            try:
                return inventory.transition_item(db, home.id, item_id, target)['status']
            except AuthProblem as error:
                return error.status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(change, ['consumed', 'discarded']))
    assert results.count(400) == 1
    with Session(postgres_engine) as db:
        assert len(inventory.list_items(db, home.id)) == 5
        assert inventory.get_item(db, home.id, item_id)['status'] in ('consumed', 'discarded')


def test_extended_edit_and_concurrent_zone_creation(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import text
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Full edits')
        items = inventory.add_batch(db, home.id, [ItemCreate(name='Rice'), ItemCreate(name='Milk')])
    def edit(item):
        with Session(postgres_engine) as db:
            return inventory.update_item(db, home.id, item['id'], ItemUpdate(
                name='Corrected ' + item['name'], category='Corrected', storage_zone='fridge', quantity='2.125'))
    with ThreadPoolExecutor(2) as pool:
        rows = list(pool.map(edit, items))
    assert rows[0]['storage_location_id'] == rows[1]['storage_location_id']
    assert all(row['storage_zone'] == 'fridge' for row in rows)
    with Session(postgres_engine) as db:
        before = db.execute(text('SELECT updated_at FROM inventory_items WHERE id=:id'), {'id': items[0]['id']}).scalar()
        row = inventory.update_item(db, home.id, items[0]['id'], ItemUpdate(status='discarded', storage_zone='freezer'))
        after = db.execute(text('SELECT updated_at FROM inventory_items WHERE id=:id'), {'id': items[0]['id']}).scalar()
        assert after > before and row['status'] == 'discarded' and row['storage_zone'] == 'freezer'
        assert len(inventory.list_items(db, home.id, zone='fridge')) == 1


def test_concurrent_create_defaults_and_explicit_zones(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Create zones')
    def create(index):
        with Session(postgres_engine) as db:
            return inventory.add_item(db, home.id, ItemCreate(name=f'Food {index}', storage_zone='freezer'))
    with ThreadPoolExecutor(2) as pool:
        rows = list(pool.map(create, range(2)))
    assert rows[0]['storage_location_id'] == rows[1]['storage_location_id']
    with Session(postgres_engine) as db:
        assert len(inventory.list_items(db, home.id, zone='freezer')) == 2
        default = inventory.add_item(db, home.id, ItemCreate(name='Rice'))
        assert default['storage_zone'] == 'pantry'


def test_transition_timestamp_and_rejected_repeat(postgres_engine):
    from sqlalchemy import text
    import pytest
    from app.core.auth_errors import AuthProblem
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Status timestamps')
        row = inventory.add_item(db, home.id, ItemCreate(name='Bread'))
        query = text('SELECT updated_at FROM inventory_items WHERE id=:id')
        before = db.execute(query, {'id': row['id']}).scalar()
        db.commit()
        inventory.transition_item(db, home.id, row['id'], 'discarded')
        after = db.execute(query, {'id': row['id']}).scalar()
        assert after > before
        db.commit()
        with pytest.raises(AuthProblem) as error:
            inventory.transition_item(db, home.id, row['id'], 'discarded')
        assert error.value.status_code == 400
        assert db.execute(query, {'id': row['id']}).scalar() == after
    with Session(postgres_engine) as phone:
        assert inventory.list_items(phone, home.id) == []
        assert inventory.list_items(phone, home.id, status='discarded')[0]['id'] == row['id']
