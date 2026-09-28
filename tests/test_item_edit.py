from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.test_household_inventory import inventory_api, HOME, OTHER, MEMBER, OUTSIDER

HEADERS = {'X-Household-ID': HOME}


def test_all_fields_and_shared_catalogue_isolation(inventory_api):
    client, identity, engine = inventory_api
    item = client.post('/api/v1/items', headers=HEADERS, json={'name': 'Milk'}).json()
    sibling = str(uuid4())
    with engine.begin() as db:
        food = db.execute(text('SELECT food_id FROM inventory_items WHERE id=:id'), {'id': item['id']}).scalar()
        db.execute(text('UPDATE foods SET avg_shelf_life_days=7 WHERE id=:id'), {'id': food})
        db.execute(text("INSERT INTO inventory_items(id, household_id, food_id, quantity, unit, status) VALUES (:id,:home,:food,1,'units','active')"),
                   {'id': sibling, 'home': OTHER, 'food': food})
    identity['id'] = MEMBER
    url = '/api/v1/items/' + item['id']
    response = client.patch(url, headers=HEADERS, json={'name': ' Oat milk ', 'category': 'Dairy alternative',
        'quantity': '2.125', 'unit': 'litres', 'expiry_date': '2026-10-10', 'storage_zone': 'fridge'})
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited['name'] == 'Oat milk' and edited['category'] == 'Dairy alternative'
    assert edited['storage_zone'] == 'fridge' and edited['storage_location_id']
    assert edited['quantity'] == '2.125' and edited['unit'] == 'litres'
    assert client.get('/api/v1/items?zone=fridge', headers=HEADERS).json()[0]['id'] == item['id']
    with engine.connect() as db:
        assert db.execute(text('SELECT name FROM foods WHERE id=:id'), {'id': food}).scalar() == 'Milk'
        assert db.execute(text('SELECT food_id FROM inventory_items WHERE id=:id'), {'id': sibling}).scalar() == food
    with engine.connect() as db:
        assert db.execute(text('SELECT f.avg_shelf_life_days FROM foods f JOIN inventory_items i ON f.id=i.food_id WHERE i.id=:id'), {'id': item['id']}).scalar() == 7
    response = client.patch(url, headers=HEADERS, json={'expiry_date': None})
    expected = dict(edited, expiry_date=None)
    assert response.json() == expected
    assert client.patch(url, headers=HEADERS, json={'storage_zone': 'freezer', 'status': 'consumed'}).json()['status'] == 'consumed'
    assert client.patch(url, headers=HEADERS, json={'status': 'consumed'}).status_code == 200
    assert client.patch(url, headers=HEADERS, json={'status': 'active'}).status_code == 409
    identity['id'] = OUTSIDER
    assert client.patch(url, headers={'X-Household-ID': OTHER}, json={'name': 'Stolen'}).status_code == 404
    assert client.patch(url, headers=HEADERS, json={'name': 'Stolen'}).status_code == 403


@pytest.mark.parametrize('patch', [{'name': ''}, {'name': None}, {'category': ' '}, {'category': None},
    {'storage_zone': 'garage'}, {'storage_zone': None}, {'status': None}, {'status': 'expired'},
    {'storage_zone': 'pantry', 'storage_location_id': None}])
def test_invalid_extended_patches(inventory_api, patch):
    client, _, _ = inventory_api
    item = client.post('/api/v1/items', headers=HEADERS, json={'name': 'Rice'}).json()
    assert client.patch('/api/v1/items/' + item['id'], headers=HEADERS, json=patch).status_code == 422
    assert client.get('/api/v1/items', headers=HEADERS).json() == [item]


def test_failed_location_does_not_leave_label_changes(inventory_api):
    client, _, engine = inventory_api
    item = client.post('/api/v1/items', headers=HEADERS, json={'name': 'Rice'}).json()
    response = client.patch('/api/v1/items/' + item['id'], headers=HEADERS,
                            json={'name': 'Changed', 'storage_location_id': str(uuid4())})
    assert response.status_code == 404
    assert response.headers['content-type'] == 'application/problem+json'
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM foods')).scalar() == 1
    assert client.get('/api/v1/items', headers=HEADERS).json() == [item]
