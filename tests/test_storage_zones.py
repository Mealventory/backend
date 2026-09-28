from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.test_household_inventory import inventory_api, HOME, OTHER

HEADERS = {'X-Household-ID': HOME}


def test_create_zones_and_filter(inventory_api):
    client, _, engine = inventory_api
    for zone in ('pantry', 'fridge', 'freezer', 'spicerack'):
        response = client.post('/api/v1/items', headers=HEADERS,
                               json={'name': zone, 'storage_zone': zone})
        assert response.status_code == 201, response.text
        row = response.json()
        assert row['storage_zone'] == zone
        assert client.get('/api/v1/items?zone=' + zone, headers=HEADERS).json() == [row]
    default = client.post('/api/v1/items', headers=HEADERS, json={'name': 'Milk', 'category': 'Dairy'}).json()
    assert default['storage_zone'] == 'pantry'
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM storage_locations')).scalar() == 4


def test_existing_unlocated_items_and_batch_rollback(inventory_api):
    client, _, engine = inventory_api
    row = client.post('/api/v1/items', headers=HEADERS, json={'name': 'Old item'}).json()
    with engine.begin() as db:
        db.execute(text('UPDATE inventory_items SET storage_location_id=NULL WHERE id=:id'), {'id': row['id']})
    listed = client.get('/api/v1/items', headers=HEADERS).json()
    assert listed[0]['storage_zone'] is None
    assert client.get('/api/v1/items?zone=pantry', headers=HEADERS).json() == []
    response = client.post('/api/v1/items/batch', headers=HEADERS, json=[
        {'name': 'Rollback', 'storage_zone': 'freezer'},
        {'name': 'Bad', 'storage_location_id': str(uuid4())}])
    assert response.status_code == 404
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM storage_locations')).scalar() == 1
        assert db.execute(text('SELECT count(*) FROM foods')).scalar() == 1


def test_location_precedence_and_isolation(inventory_api):
    client, _, engine = inventory_api
    location, foreign = str(uuid4()), str(uuid4())
    with engine.begin() as db:
        db.execute(text('INSERT INTO storage_locations(id,household_id,zone,name) VALUES (:id,:home,:zone,:name)'), [
            dict(id=location, home=HOME, zone='fridge', name='Custom'),
            dict(id=foreign, home=OTHER, zone='freezer', name='Other')])
    row = client.post('/api/v1/items', headers=HEADERS,
                      json={'name': 'Milk', 'storage_location_id': location}).json()
    assert row['storage_zone'] == 'fridge' and row['storage_location_id'] == location
    assert client.post('/api/v1/items', headers=HEADERS,
        json={'name': 'Milk', 'storage_zone': 'fridge', 'storage_location_id': location}).status_code == 422
    assert client.post('/api/v1/items', headers=HEADERS,
        json={'name': 'Milk', 'storage_location_id': foreign}).status_code == 404


@pytest.mark.parametrize('zone', ['garage', '', 'FRIDGE', 123])
def test_invalid_zone_returns_400_without_changes(inventory_api, zone):
    client, _, engine = inventory_api
    assert client.post('/api/v1/items', headers=HEADERS,
                      json={'name': 'Rice', 'storage_zone': zone}).status_code == 400
    row = client.post('/api/v1/items', headers=HEADERS, json={'name': 'Rice'}).json()
    assert client.patch('/api/v1/items/' + row['id'], headers=HEADERS,
                        json={'storage_zone': zone}).status_code == 400
    assert client.get('/api/v1/items', headers=HEADERS, params={'zone': zone}).status_code == 400
    assert client.get('/api/v1/items', headers=HEADERS).json() == [row]
