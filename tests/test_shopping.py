"""Household shopping API contract and persistence tests."""
import pytest
from sqlalchemy import text
from app.models.shopping import ShoppingListItem
from app.core.dependencies import get_current_user
from app.main import app
from tests.test_household_inventory import inventory_api, OWNER, MEMBER, OUTSIDER, HOME, OTHER

PATH = '/api/v1/shopping'
HEADERS = {'X-Household-ID': HOME}


@pytest.fixture
def shopping_api(inventory_api):
    client, identity, engine = inventory_api
    ShoppingListItem.__table__.create(engine)
    return client, identity, engine


def test_member_crud_visible_between_requests(shopping_api):
    client, identity, engine = shopping_api
    assert client.get(PATH, headers=HEADERS).json() == []
    response = client.post(PATH, headers=HEADERS, json={'name': ' Milk ', 'quantity': '2.125', 'unit': ' bottles '})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item['name'] == 'Milk' and item['unit'] == 'bottles'
    assert item['checked'] is False and item['food_id'] is None
    assert item['household_id'] == HOME and item['created_at'] and item['updated_at']
    activity = client.get('/api/v1/activity', headers=HEADERS).json()
    assert activity[0]['action'] == 'shopping_added'
    assert activity[0]['item_name'] == 'Milk'
    assert activity[0]['entity_type'] == 'shopping'
    identity['id'] = MEMBER
    assert client.get(PATH, headers=HEADERS).json() == [item]
    url = PATH + '/' + item['id']
    response = client.patch(url, headers=HEADERS, json={'checked': True, 'quantity': '3.5'})
    assert response.status_code == 200, response.text
    assert response.json()['checked'] is True
    assert response.json()['quantity'] == '3.5'
    assert response.json()['unit'] == 'bottles'
    assert client.patch(url, headers=HEADERS, json={'checked': True}).json()['checked'] is True
    assert client.patch(url, headers=HEADERS, json={'checked': False, 'unit': 'litres'}).json()['checked'] is False
    identity['id'] = OWNER
    assert client.get(PATH, headers=HEADERS).json()[0]['unit'] == 'litres'
    response = client.delete(url, headers=HEADERS)
    assert response.status_code == 204 and response.content == b''
    assert client.get(PATH, headers=HEADERS).json() == []
    assert client.delete(url, headers=HEADERS).status_code == 404
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM shopping_list_items')).scalar() == 0


def test_household_isolation_and_clear_checked(shopping_api):
    client, identity, _ = shopping_api
    item = client.post(PATH, headers=HEADERS, json={'name': 'Rice'}).json()
    keep = client.post(PATH, headers=HEADERS, json={'name': 'Beans'}).json()
    url = PATH + '/' + item['id']
    client.patch(url, headers=HEADERS, json={'checked': True})
    identity['id'] = OUTSIDER
    other_headers = {'X-Household-ID': OTHER}
    for method, path, payload in [('get', PATH, None), ('post', PATH, {'name': 'Bad'}),
                                  ('patch', url, {'checked': False}), ('delete', url, None),
                                  ('post', PATH + '/clear-checked', None)]:
        response = client.request(method, path, headers=HEADERS, json=payload)
        assert response.status_code == 403
    assert client.get(PATH, headers=other_headers).json() == []
    assert client.patch(url, headers=other_headers, json={'checked': False}).status_code == 404
    assert client.delete(url, headers=other_headers).status_code == 404
    foreign = client.post(PATH, headers=other_headers, json={'name': 'Foreign'}).json()
    client.patch(PATH + '/' + foreign['id'], headers=other_headers, json={'checked': True})
    identity['id'] = MEMBER
    assert client.post(PATH + '/clear-checked', headers=HEADERS).json() == {'deleted_count': 1}
    assert client.post(PATH + '/clear-checked', headers=HEADERS).json() == {'deleted_count': 0}
    assert [x['id'] for x in client.get(PATH, headers=HEADERS).json()] == [keep['id']]
    identity['id'] = OUTSIDER
    assert client.get(PATH, headers=other_headers).json()[0]['id'] == foreign['id']


@pytest.mark.parametrize('body', [{'name': ''}, {'name': '  '}, {'name': 'x', 'quantity': 0},
    {'name': 'x', 'quantity': -1}, {'name': 'x', 'quantity': 'NaN'}, {'name': 'x', 'quantity': '1.0001'},
    {'name': 'x', 'quantity': '1000000000'}, {'name': 'x', 'unit': ' '}, {'name': 'x', 'household_id': OTHER},
    {'name': 'x', 'added_by': OWNER}, {'name': 'x', 'food_id': 'invalid'}])
def test_invalid_create(shopping_api, body):
    assert shopping_api[0].post(PATH, headers=HEADERS, json=body).status_code == 422


@pytest.mark.parametrize('body', [{}, {'checked': None}, {'checked': 'false'}, {'quantity': None},
    {'quantity': 0}, {'quantity': '1.0001'}, {'unit': None}, {'unit': ' '}, {'name': 'rename'}, {'is_checked': True}])
def test_invalid_patch(shopping_api, body):
    client, _, _ = shopping_api
    item = client.post(PATH, headers=HEADERS, json={'name': 'Milk'}).json()
    assert client.patch(PATH + '/' + item['id'], headers=HEADERS, json=body).status_code == 422
    assert client.get(PATH, headers=HEADERS).json() == [item]


def test_food_link_and_authentication(shopping_api):
    client, _, engine = shopping_api
    food_id = '30000000-0000-0000-0000-000000000001'
    assert client.post(PATH, headers=HEADERS, json={'name': 'Milk', 'food_id': food_id}).status_code == 404
    with engine.begin() as db:
        db.execute(text("INSERT INTO foods (id,name,default_unit) VALUES (:id,'Milk','units')"), {'id': food_id})
    response = client.post(PATH, headers=HEADERS, json={'name': 'Milk', 'food_id': food_id})
    assert response.status_code == 201 and response.json()['food_id'] == food_id
    assert client.get(PATH).status_code == 400
    assert client.get(PATH, headers={'X-Household-ID': 'invalid'}).status_code == 400
    assert client.patch(PATH + '/invalid', headers=HEADERS, json={'checked': True}).status_code == 422
    app.dependency_overrides.pop(get_current_user)
    for method, path, payload in [('get', PATH, None), ('post', PATH, {'name': 'x'}),
        ('patch', PATH + '/' + response.json()['id'], {'checked': True}),
        ('delete', PATH + '/' + response.json()['id'], None), ('post', PATH + '/clear-checked', None)]:
        assert client.request(method, path, headers=HEADERS, json=payload).status_code == 401
