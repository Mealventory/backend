import pytest
from app.models.saved_recipe import SavedRecipe
from tests.test_household_inventory import inventory_api, OWNER, MEMBER, OUTSIDER, HOME, OTHER

PATH = '/api/v1/recipes/saved'
HEADERS = {'X-Household-ID': HOME}
RECIPE = dict(id='generated-1', name='Soup', time='20 min', difficulty='Easy', match=80,
              uses=['Carrot'], emoji='🍲', tag='Pantry', description='Use carrots', steps=['Cook'])


@pytest.fixture
def saved_api(inventory_api):
    client, identity, engine = inventory_api
    SavedRecipe.__table__.create(engine)
    return client, identity


def test_household_sharing_idempotency_and_isolation(saved_api):
    client, identity = saved_api
    for _ in range(2):
        assert client.put(PATH, headers=HEADERS, json=RECIPE).status_code == 204
    identity['id'] = MEMBER
    rows = client.get(PATH, headers=HEADERS).json()
    assert len(rows) == 1 and rows[0]['name'] == 'Soup'
    assert rows[0]['id'].startswith('saved-')
    identity['id'] = OUTSIDER
    assert client.get(PATH, headers=HEADERS).status_code == 403
    assert client.put(PATH, headers=HEADERS, json=RECIPE).status_code == 403
    assert client.post(PATH + '/remove', headers=HEADERS, json=RECIPE).status_code == 403
    assert client.get(PATH, headers={'X-Household-ID': OTHER}).json() == []
    assert client.post(PATH + '/remove', headers={'X-Household-ID': OTHER}, json=RECIPE).status_code == 204
    identity['id'] = MEMBER
    assert len(client.get(PATH, headers=HEADERS).json()) == 1
    assert client.post(PATH + '/remove', headers=HEADERS, json=rows[0]).status_code == 204
    identity['id'] = OWNER
    assert client.get(PATH, headers=HEADERS).json() == []


@pytest.mark.parametrize('patch', [{'name': ''}, {'match': 101}, {'steps': ['x' * 4001]}, {'household_id': OTHER}])
def test_invalid_snapshot(saved_api, patch):
    assert saved_api[0].put(PATH, headers=HEADERS, json={**RECIPE, **patch}).status_code == 422
