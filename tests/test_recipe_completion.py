import pytest
from sqlalchemy import text
from tests.test_household_inventory import inventory_api, HOME, OTHER, OWNER, MEMBER, OUTSIDER


@pytest.fixture
def meal_api(inventory_api):
    client, identity, engine = inventory_api
    with engine.begin() as c:
        c.execute(text('''CREATE TABLE household_recipe_completions (household_id text,
            completion_id text, fingerprint text NOT NULL, result text,
            PRIMARY KEY (household_id, completion_id))'''))
    return client, identity, engine


def pantry(client, name='Rice', quantity=5, unit='cups', home=HOME):
    return client.post('/api/v1/items', headers={'X-Household-ID': home}, json={
        'name': name, 'quantity': quantity, 'unit': unit}).json()


def review(*rows):
    return {'completion_id': 'meal-unique-request-12345', 'recipe_id': 'recipe-1',
            'recipe_name': 'Rice bowl', 'items': [{'item_id': row['id'], 'quantity': '2',
                'expected_quantity': row['quantity'], 'unit': row['unit']} for row in rows]}


def submit(client, request, home=HOME):
    return client.post('/api/v1/recipes/complete', headers={'X-Household-ID': home}, json=request)


def test_member_completion_partial_full_history_and_retry(meal_api):
    client, identity, _ = meal_api
    rice, eggs = pantry(client), pantry(client, 'Eggs', 2, 'eggs')
    request = review(rice, eggs)
    identity['id'] = MEMBER
    saved = submit(client, request)
    assert saved.status_code == 200, saved.text
    assert submit(client, request).json() == saved.json()
    identity['id'] = OWNER
    active = client.get('/api/v1/items', headers={'X-Household-ID': HOME}).json()
    assert len(active) == 1 and active[0]['quantity'] == '3'
    consumed = client.get('/api/v1/items?status=consumed', headers={'X-Household-ID': HOME}).json()
    assert consumed[0]['id'] == eggs['id'] and consumed[0]['quantity'] == '2'
    request['items'][0]['quantity'] = '1'
    assert submit(client, request).status_code == 409


def test_atomic_failure_and_stale_review(meal_api):
    client, _, engine = meal_api
    a, b = pantry(client), pantry(client, 'Milk', 1)
    # Sort ensures the valid item is processed first, exercising rollback of a write.
    rows = sorted([a, b], key=lambda row: row['id'])
    request = review(*rows)
    request['items'][0]['quantity'] = '0.5'
    request['items'][1]['quantity'] = '100'
    assert submit(client, request).status_code == 409
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM household_recipe_completions')).scalar() == 0
    active = client.get('/api/v1/items', headers={'X-Household-ID': HOME}).json()
    assert {r['id']: r['quantity'] for r in active} == {a['id']: a['quantity'], b['id']: b['quantity']}
    request = review(a)
    client.patch('/api/v1/items/' + a['id'], headers={'X-Household-ID': HOME}, json={'quantity': 4})
    assert submit(client, request).status_code == 409
    request['items'][0]['expected_quantity'] = '4'
    request['items'][0]['unit'] = 'kg'
    assert submit(client, request).status_code == 409


def test_household_auth_and_validation(meal_api):
    client, identity, _ = meal_api
    request = review(pantry(client))
    identity['id'] = OUTSIDER
    assert submit(client, request).status_code == 403
    assert submit(client, request, OTHER).status_code == 404
    identity['id'] = OWNER
    assert client.post('/api/v1/recipes/complete', json=request).status_code == 400
    for quantity in ['0', '-1', 'NaN', '1.0001']:
        request['items'][0]['quantity'] = quantity
        assert submit(client, request).status_code == 422
    request['items'][0]['quantity'] = '1'
    request['items'] *= 2
    assert submit(client, request).status_code == 422
    request['items'] = []
    assert submit(client, request).status_code == 422


def test_terminal_item_and_new_meal(meal_api):
    client, _, _ = meal_api
    row = pantry(client)
    request = review(row)
    assert submit(client, request).status_code == 200
    request['completion_id'] = 'another-meal-request-12345'
    request['items'][0]['expected_quantity'] = '3'
    assert submit(client, request).status_code == 200
    client.post('/api/v1/items/' + row['id'] + '/discard', headers={'X-Household-ID': HOME})
    request['completion_id'] = 'third-meal-request-12345'
    request['items'][0]['expected_quantity'] = '1'
    assert submit(client, request).status_code == 409


def test_recipe_use_automatically_triggers_low_stock_at_ten_percent(meal_api, monkeypatch):
    client, _, _ = meal_api
    notifications = []
    monkeypatch.setattr(
        "app.services.recipe_completion_service.send_low_stock_notification",
        lambda db, household_id, item_id: notifications.append(
            (str(household_id), str(item_id))
        ),
    )
    flour = pantry(client, 'Flour', 10, 'cups')
    request = {
        'completion_id': 'low-stock-meal-request-12345',
        'recipe_id': 'bread',
        'recipe_name': 'Bread',
        'items': [{
            'item_id': flour['id'],
            'quantity': '9',
            'expected_quantity': flour['quantity'],
            'unit': flour['unit'],
        }],
    }

    completed = submit(client, request)
    assert completed.status_code == 200, completed.text

    active = client.get('/api/v1/items', headers={'X-Household-ID': HOME}).json()
    updated = next(item for item in active if item['id'] == flour['id'])
    assert updated['quantity'] == '1'
    assert float(updated['remaining_percent']) == 10
    assert updated['is_low_stock'] is True
    assert notifications == [(HOME, flour['id'])]
