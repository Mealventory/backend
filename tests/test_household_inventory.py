"""API persistence and tenant isolation checks on an isolated test database."""
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.dependencies import get_current_user
from app.dependencies.database import get_db
from app.models.household_member import HouseholdMember
from app.models.push_token import PushToken
from app.schemas.user import UserOut

OWNER = '10000000-0000-0000-0000-000000000001'
MEMBER = '10000000-0000-0000-0000-000000000002'
OUTSIDER = '10000000-0000-0000-0000-000000000003'
HOME = '20000000-0000-0000-0000-000000000001'
OTHER = '20000000-0000-0000-0000-000000000002'


@pytest.fixture
def inventory_api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    HouseholdMember.__table__.create(engine)
    PushToken.__table__.create(engine)
    with engine.begin() as c:
        c.execute(text('''CREATE TABLE storage_locations (id text PRIMARY KEY,
            household_id text NOT NULL, zone text NOT NULL, name text, UNIQUE(household_id, name))'''))
        c.execute(text('''CREATE TABLE foods (id text PRIMARY KEY, name text NOT NULL,
            category text, default_unit text NOT NULL, avg_shelf_life_days integer)'''))
        c.execute(text('''CREATE TABLE inventory_items (id text PRIMARY KEY,
            household_id text NOT NULL, food_id text NOT NULL, quantity numeric NOT NULL,
            quantity_tracking_enabled boolean NOT NULL DEFAULT 0,
            initial_quantity numeric,
            low_stock_threshold_percent numeric NOT NULL DEFAULT 10,
            low_stock_notified_at timestamp,
            unit text NOT NULL, expiry_date date, status text NOT NULL, storage_location_id text,
            image_ref text,
            created_at timestamp DEFAULT CURRENT_TIMESTAMP)'''))
        c.execute(text('''CREATE TABLE household_activity_events (
            id text PRIMARY KEY,
            household_id text NOT NULL,
            actor_user_id text NOT NULL,
            actor_name text NOT NULL,
            action text NOT NULL,
            entity_type text NOT NULL,
            entity_id text,
            item_name text NOT NULL,
            created_at timestamp DEFAULT CURRENT_TIMESTAMP)'''))
    with Session(engine) as db:
        db.add_all([HouseholdMember(household_id=HOME, user_id=OWNER, role='owner'),
                    HouseholdMember(household_id=HOME, user_id=MEMBER, role='member'),
                    HouseholdMember(household_id=OTHER, user_id=OUTSIDER, role='owner')])
        db.commit()
    identity = {'id': OWNER}
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: UserOut(id=identity['id'], email='test@example.com')
    try:
        with TestClient(app) as client:
            yield client, identity, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_member_delete_persists_and_is_visible_to_owner(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}
    created = client.post('/api/v1/items', headers=headers, json={
        'name': 'Milk', 'quantity': 2, 'unit': 'bottles', 'expiry_date': '2026-10-20'})
    assert created.status_code == 201, created.text
    item = created.json()
    UUID(item['id'])
    identity['id'] = MEMBER
    assert client.get('/api/v1/items', headers=headers).json()[0]['id'] == item['id']
    deleted = client.delete('/api/v1/items/' + item['id'], headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b''
    # Another request and a fresh DB session observe the committed deletion.
    identity['id'] = OWNER
    assert client.get('/api/v1/items', headers=headers).json() == []
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 0
        assert c.execute(text('SELECT count(*) FROM foods')).scalar() == 1
    assert client.delete('/api/v1/items/' + item['id'], headers=headers).status_code == 404


def test_cross_household_delete_is_rejected(inventory_api):
    client, identity, _ = inventory_api
    item = client.post('/api/v1/items', headers={'X-Household-ID': HOME}, json={'name': 'Rice'}).json()
    identity['id'] = OUTSIDER
    assert client.delete('/api/v1/items/' + item['id'], headers={'X-Household-ID': HOME}).status_code == 403
    assert client.delete('/api/v1/items/' + item['id'], headers={'X-Household-ID': OTHER}).status_code == 404
    assert client.get('/api/v1/items', headers={'X-Household-ID': OTHER}).json() == []
    identity['id'] = OWNER
    assert len(client.get('/api/v1/items', headers={'X-Household-ID': HOME}).json()) == 1


def test_validation_and_authentication(inventory_api):
    client, _, _ = inventory_api
    headers = {'X-Household-ID': HOME}
    for body in [{'name': ''}, {'name': 'Rice', 'quantity': -1}, {'name': 'Rice', 'household_id': OTHER}, {'name': 'Rice', 'expiry_date': '2026-02-30'}]:
        assert client.post('/api/v1/items', headers=headers, json=body).status_code == 422
    assert client.get('/api/v1/items').status_code == 400
    assert client.delete('/api/v1/items/not-a-uuid', headers=headers).status_code == 422
    app.dependency_overrides.pop(get_current_user)
    assert client.get('/api/v1/items', headers=headers).status_code == 401


def test_member_edit_and_terminal_states(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}
    row = client.post('/api/v1/items', headers=headers, json={'name': 'Milk', 'expiry_date': '2026-12-01'}).json()
    url = '/api/v1/items/' + row['id']
    identity['id'] = MEMBER
    edited = client.patch(url, headers=headers, json={'quantity': '2.5', 'unit': 'litres', 'expiry_date': None})
    assert edited.status_code == 200, edited.text
    assert edited.json()['quantity'] == '2.5'
    assert edited.json()['expiry_date'] is None
    assert edited.json()['name'] == 'Milk'
    result = client.post(url + '/consume', headers=headers)
    assert result.status_code == 200 and result.json()['status'] == 'consumed'
    for action in ('consume', 'discard'):
        result = client.post(url + '/' + action, headers=headers)
        assert result.status_code == 400
        assert result.json()['detail'] == 'Item is not active'
    assert client.patch(url, headers=headers, json={'quantity': 3}).status_code == 409
    assert client.get('/api/v1/items', headers=headers).json() == []
    assert client.get('/api/v1/items?status=consumed', headers=headers).json()[0]['id'] == row['id']
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 1


def test_batch_atomicity_filters_and_storage_isolation(inventory_api):
    from datetime import date, timedelta
    client, _, engine = inventory_api
    headers = {'X-Household-ID': HOME}
    location = '30000000-0000-0000-0000-000000000001'
    foreign = '30000000-0000-0000-0000-000000000002'
    with engine.begin() as c:
        c.execute(text('INSERT INTO storage_locations (id, household_id, zone) VALUES (:id, :home, :zone)'), [
            {'id': location, 'home': HOME, 'zone': 'fridge'},
            {'id': foreign, 'home': OTHER, 'zone': 'fridge'}])
    response = client.post('/api/v1/items/batch', headers=headers, json=[
        {'name': f'Milk {i}', 'storage_location_id': location,
         'expiry_date': (date.today() + timedelta(days=i)).isoformat()} for i in range(6)])
    assert response.status_code == 201, response.text
    assert len({item['id'] for item in response.json()}) == 6
    url = '/api/v1/items/' + response.json()[0]['id']
    assert client.patch(url, headers=headers, json={'storage_location_id': foreign}).status_code == 404
    assert len(client.get('/api/v1/items?zone=fridge&expiring_days=2&search=mIlK', headers=headers).json()) == 3
    assert client.get('/api/v1/items?zone=freezer', headers=headers).json() == []
    assert client.get('/api/v1/items?search=%25', headers=headers).json() == []
    failed = client.post('/api/v1/items/batch', headers=headers, json=[
        {'name': 'Must roll back'}, {'name': 'Bad location', 'storage_location_id': foreign}])
    assert failed.status_code == 404
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 6
        assert c.execute(text('SELECT count(*) FROM foods')).scalar() == 6
    assert client.patch(url, headers=headers, json={'storage_location_id': None}).json()['storage_location_id'] is None
    assert client.post(url + '/discard', headers=headers).json()['status'] == 'discarded'


def test_edit_validation_and_tenant_isolation(inventory_api):
    client, identity, _ = inventory_api
    headers = {'X-Household-ID': HOME}
    row = client.post('/api/v1/items', headers=headers, json={'name': 'Rice'}).json()
    url = '/api/v1/items/' + row['id']
    for patch in [{}, {'quantity': None}, {'quantity': 0}, {'quantity': 'NaN'},
                  {'quantity': '1.0001'}, {'unit': ''}, {'unit': None},
                  {'expiry_date': '2026-02-30'}, {'status': 'invalid'},
                  {'quantity_tracking_enabled': False}, {'initial_quantity': 2},
                  {'low_stock_threshold_percent': 5},
                  {'household_id': OTHER}]:
        assert client.patch(url, headers=headers, json=patch).status_code == 422, patch
    for items in [[], [{'name': 'Rice'}] * 101, [{'name': 'Rice'}, {'name': ''}]]:
        assert client.post('/api/v1/items/batch', headers=headers, json=items).status_code == 422
    for query in ['status=expired', 'expiring_days=-1']:
        assert client.get('/api/v1/items?' + query, headers=headers).status_code == 422
    identity['id'] = OUTSIDER
    for home, expected in [(HOME, 403), (OTHER, 404)]:
        assert client.patch(url, headers={'X-Household-ID': home}, json={'quantity': 4}).status_code == expected
        for action in ['consume', 'discard']:
            assert client.post(url + '/' + action, headers={'X-Household-ID': home}).status_code == expected


def test_low_stock_tracking_is_automatic_fixed_and_household_scoped(inventory_api):
    client, identity, _ = inventory_api
    headers = {'X-Household-ID': HOME}
    created = client.post('/api/v1/items', headers=headers, json={
        'name': 'Flour',
        'quantity': 2,
        'unit': 'kg',
    })
    assert created.status_code == 201, created.text
    item = created.json()
    assert float(item['remaining_percent']) == 100
    assert item['is_low_stock'] is False

    url = '/api/v1/items/' + item['id']
    low = client.patch(url, headers=headers, json={'quantity': 0.2})
    assert low.status_code == 200, low.text
    assert float(low.json()['remaining_percent']) == 10
    assert low.json()['is_low_stock'] is True

    above = client.patch(url, headers=headers, json={'quantity': 0.21})
    assert above.status_code == 200, above.text
    assert float(above.json()['remaining_percent']) == 10.5
    assert above.json()['is_low_stock'] is False

    # Threshold/reference configuration is internal; clients cannot override it.
    for patch in [
        {'quantity_tracking_enabled': False},
        {'initial_quantity': 5},
        {'low_stock_threshold_percent': 50},
    ]:
        assert client.patch(url, headers=headers, json=patch).status_code == 422

    identity['id'] = OUTSIDER
    assert client.get('/api/v1/items', headers={'X-Household-ID': OTHER}).json() == []
    assert client.patch(url, headers={'X-Household-ID': OTHER}, json={'quantity': 0.1}).status_code == 404


def test_discard_history_visible_to_another_member(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}
    row = client.post('/api/v1/items', headers=headers, json={'name': 'Bread'}).json()
    identity['id'] = MEMBER
    url = '/api/v1/items/' + row['id']
    assert client.post(url + '/discard', headers=headers).json()['status'] == 'discarded'
    identity['id'] = OWNER
    assert client.get('/api/v1/items', headers=headers).json() == []
    assert client.get('/api/v1/items?status=discarded', headers=headers).json()[0]['id'] == row['id']
    for action in ('consume', 'discard'):
        assert client.post(url + '/' + action, headers=headers).status_code == 400
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 1


def test_item_image_reference_create_update_clear_and_household_scope(inventory_api):
    client, identity, _ = inventory_api
    headers = {'X-Household-ID': HOME}
    storage_ref = f'{HOME}/milk-photo.jpg'

    created = client.post('/api/v1/items', headers=headers, json={
        'name': 'Milk',
        'category': 'Dairy',
        'image_ref': storage_ref,
    })
    assert created.status_code == 201, created.text
    item = created.json()
    assert item['image_ref'] == storage_ref

    remote = 'https://images.openfoodfacts.org/images/products/test.jpg'
    updated = client.patch(
        '/api/v1/items/' + item['id'],
        headers=headers,
        json={'image_ref': remote},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()['image_ref'] == remote

    cleared = client.patch(
        '/api/v1/items/' + item['id'],
        headers=headers,
        json={'image_ref': None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()['image_ref'] is None

    for invalid in [
        '',
        'http://example.com/photo.jpg',
        '/absolute/path.jpg',
        '../escape.jpg',
        f'{OTHER}/foreign-photo.jpg',
    ]:
        response = client.patch(
            '/api/v1/items/' + item['id'],
            headers=headers,
            json={'image_ref': invalid},
        )
        assert response.status_code in (400, 422), (invalid, response.text)

    identity['id'] = OUTSIDER
    assert client.patch(
        '/api/v1/items/' + item['id'],
        headers={'X-Household-ID': OTHER},
        json={'image_ref': f'{OTHER}/attempt.jpg'},
    ).status_code == 404


def test_add_item_stacks_identical_item(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}

    first = client.post('/api/v1/items', headers=headers, json={
        'name': 'Apples',
        'quantity': 2,
        'unit': 'pieces',
        'expiry_date': '2026-10-25',
        'storage_zone': 'fridge',
    })
    assert first.status_code == 201, first.text
    first_item = first.json()
    assert float(first_item['quantity']) == 2.0

    # Post identical item with whitespace and case variations
    second = client.post('/api/v1/items', headers=headers, json={
        'name': ' apples  ',
        'quantity': 3,
        'unit': ' pieces ',
        'expiry_date': '2026-10-25',
        'storage_zone': 'fridge',
    })
    assert second.status_code == 201, second.text
    second_item = second.json()

    assert second_item['id'] == first_item['id']
    assert float(second_item['quantity']) == 5.0

    with engine.connect() as c:
        initial = c.execute(text('SELECT initial_quantity FROM inventory_items WHERE id = :id'), {'id': second_item['id']}).scalar()
        assert float(initial) == 5.0

    # Verify only 1 item exists in DB
    items = client.get('/api/v1/items', headers=headers).json()
    assert len(items) == 1
    assert items[0]['id'] == first_item['id']
    assert float(items[0]['quantity']) == 5.0


def test_add_item_does_not_stack_when_attributes_differ(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}

    base = client.post('/api/v1/items', headers=headers, json={
        'name': 'Milk',
        'quantity': 1,
        'unit': 'liters',
        'expiry_date': '2026-10-20',
        'storage_zone': 'fridge',
    })
    assert base.status_code == 201

    # Differing expiry date
    diff_expiry = client.post('/api/v1/items', headers=headers, json={
        'name': 'Milk',
        'quantity': 1,
        'unit': 'liters',
        'expiry_date': '2026-10-25',
        'storage_zone': 'fridge',
    })
    assert diff_expiry.status_code == 201
    assert diff_expiry.json()['id'] != base.json()['id']

    # Differing unit
    diff_unit = client.post('/api/v1/items', headers=headers, json={
        'name': 'Milk',
        'quantity': 1,
        'unit': 'bottles',
        'expiry_date': '2026-10-20',
        'storage_zone': 'fridge',
    })
    assert diff_unit.status_code == 201
    assert diff_unit.json()['id'] != base.json()['id']

    # Differing zone
    diff_zone = client.post('/api/v1/items', headers=headers, json={
        'name': 'Milk',
        'quantity': 1,
        'unit': 'liters',
        'expiry_date': '2026-10-20',
        'storage_zone': 'pantry',
    })
    assert diff_zone.status_code == 201
    assert diff_zone.json()['id'] != base.json()['id']

    items = client.get('/api/v1/items', headers=headers).json()
    assert len(items) == 4


def test_add_item_does_not_stack_with_inactive_items(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}

    created = client.post('/api/v1/items', headers=headers, json={
        'name': 'Bananas',
        'quantity': 3,
        'unit': 'pieces',
    })
    assert created.status_code == 201
    item_id = created.json()['id']

    # Mark consumed/deleted
    del_resp = client.delete(f'/api/v1/items/{item_id}', headers=headers)
    assert del_resp.status_code == 204

    # Add again - should create a fresh active item, not update the deleted one
    recreated = client.post('/api/v1/items', headers=headers, json={
        'name': 'Bananas',
        'quantity': 2,
        'unit': 'pieces',
    })
    assert recreated.status_code == 201
    assert recreated.json()['id'] != item_id
    assert float(recreated.json()['quantity']) == 2.0


def test_batch_add_intra_batch_and_existing_stacking(inventory_api):
    client, identity, engine = inventory_api
    headers = {'X-Household-ID': HOME}

    batch_payload = [
        {'name': 'Greek Yogurt', 'quantity': 1, 'unit': 'tubs', 'storage_zone': 'fridge'},
        {'name': 'Greek Yogurt', 'quantity': 2, 'unit': 'tubs', 'storage_zone': 'fridge'},
        {'name': 'Eggs', 'quantity': 6, 'unit': 'pieces', 'storage_zone': 'fridge'},
    ]
    batch_resp = client.post('/api/v1/items/batch', headers=headers, json=batch_payload)
    assert batch_resp.status_code == 201, batch_resp.text
    rows = batch_resp.json()
    # Batch collapses intra-batch duplicates into 1 item
    assert len(rows) == 2

    yogurt = next(r for r in rows if r['name'] == 'Greek Yogurt')
    assert float(yogurt['quantity']) == 3.0

    # Add another batch that stacks into the existing yogurt
    batch_resp2 = client.post('/api/v1/items/batch', headers=headers, json=[
        {'name': 'Greek Yogurt', 'quantity': 1.5, 'unit': 'tubs', 'storage_zone': 'fridge'},
    ])
    assert batch_resp2.status_code == 201
    rows2 = batch_resp2.json()
    assert len(rows2) == 1
    assert rows2[0]['id'] == yogurt['id']
    assert float(rows2[0]['quantity']) == 4.5
