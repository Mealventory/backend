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


def test_low_stock_tracking_uses_persisted_reference_quantity(postgres_engine):
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Low stock')
        row = inventory.add_item(db, home.id, ItemCreate(
            name='Flour',
            quantity='2',
            unit='kg',
        ))
        from sqlalchemy import text
        assert str(db.execute(
            text('SELECT initial_quantity FROM inventory_items WHERE id=:id'),
            {'id': row['id']},
        ).scalar_one()) == '2.000'
        assert str(row['remaining_percent']) == '100.0'
        assert row['is_low_stock'] is False

        low = inventory.update_item(
            db,
            home.id,
            row['id'],
            ItemUpdate(quantity='0.2'),
        )
        assert str(low['remaining_percent']) == '10.0'
        assert low['is_low_stock'] is True


def test_stale_quantity_patch_and_independent_items(postgres_engine):
    """Two devices editing the same read version cannot both commit."""
    from concurrent.futures import ThreadPoolExecutor
    from app.core.auth_errors import AuthProblem

    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Versioned stock')
        milk = inventory.add_item(db, home.id, ItemCreate(name='Milk', quantity='4'))
        bread = inventory.add_item(db, home.id, ItemCreate(name='Bread'))
    assert milk['version'] == bread['version'] == 1

    def edit(amount):
        with Session(postgres_engine) as db:
            try:
                return inventory.update_item(
                    db, home.id, milk['id'], ItemUpdate(quantity=amount),
                    expected_version=milk['version'],
                )['version']
            except AuthProblem as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ['2', '3']))
    assert sorted(results) == [2, 409]

    with Session(postgres_engine) as db:
        fresh = inventory.get_item(db, home.id, milk['id'])
        assert fresh['version'] == 2
        assert str(fresh['quantity']) in ('2.000', '3.000')
        other = inventory.update_item(
            db, home.id, bread['id'], ItemUpdate(quantity='5'),
            expected_version=bread['version'],
        )
        assert other['version'] == 2
        assert str(other['quantity']) == '5.000'


def test_version_changes_for_stack_merge_and_terminal_status(postgres_engine):
    from app.core.auth_errors import AuthProblem

    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Version mutation')
        item = inventory.add_item(db, home.id, ItemCreate(name='Rice', quantity='2'))
        # Adding an identical item stacks onto the original row.
        stacked = inventory.add_item(db, home.id, ItemCreate(name='Rice', quantity='1'))
        assert stacked['id'] == item['id']
        assert stacked['version'] == item['version'] + 1
        with __import__('pytest').raises(AuthProblem) as stale:
            inventory.update_item(
                db, home.id, item['id'], ItemUpdate(quantity='10'),
                expected_version=item['version'],
            )
        assert stale.value.status_code == 409

        moved = inventory.update_item(
            db, home.id, stacked['id'], ItemUpdate(storage_zone='fridge'),
            expected_version=stacked['version'],
        )
        assert moved['version'] == stacked['version'] + 1
        consumed = inventory.transition_item(db, home.id, moved['id'], 'consumed')
        assert consumed['version'] == moved['version'] + 1
        with __import__('pytest').raises(AuthProblem) as inactive:
            inventory.update_item(
                db, home.id, moved['id'], ItemUpdate(quantity='12'),
                expected_version=moved['version'],
            )
        assert inactive.value.status_code == 409


def test_edit_merge_changes_target_version_and_deletes_source(postgres_engine):
    import pytest
    from app.core.auth_errors import AuthProblem

    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Merge after read')
        source = inventory.add_item(db, home.id, ItemCreate(name='Bread', quantity='2'))
        target = inventory.add_item(db, home.id, ItemCreate(name='Milk', quantity='1'))
        merged = inventory.update_item(
            db, home.id, source['id'], ItemUpdate(name='Milk'),
            expected_version=source['version'],
        )
        assert str(merged['id']) == str(target['id'])
        assert merged['version'] == target['version'] + 1
        with pytest.raises(AuthProblem) as gone:
            inventory.update_item(
                db, home.id, source['id'], ItemUpdate(quantity='7'),
                expected_version=source['version'],
            )
        assert gone.value.status_code == 404
        with pytest.raises(AuthProblem) as stale_target:
            inventory.update_item(
                db, home.id, target['id'], ItemUpdate(quantity='7'),
                expected_version=target['version'],
            )
        assert stale_target.value.status_code == 409
