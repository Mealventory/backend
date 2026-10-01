import pytest
from sqlalchemy.orm import Session
from app.models.push_token import PushToken
from tests.test_household_inventory import inventory_api, OWNER, MEMBER

PATH = '/api/v1/notifications/device'
TOKEN = 'ExpoPushToken[test-device-1]'

@pytest.fixture
def push_api(inventory_api):
    client, identity, engine = inventory_api
    PushToken.__table__.create(engine)
    return client, identity, engine

def test_registration_transfer_and_owner_scoped_cleanup(push_api):
    client, identity, engine = push_api
    for _ in range(2):
        assert client.put(PATH, json={'token': TOKEN, 'platform': 'ios'}).status_code == 204
    with Session(engine) as db:
        assert db.query(PushToken).count() == 1
        assert db.query(PushToken).one().user_id == OWNER
    identity['id'] = MEMBER
    assert client.put(PATH, json={'token': TOKEN, 'platform': 'android'}).status_code == 204
    identity['id'] = OWNER
    assert client.post(PATH+'/remove', json={'token': TOKEN}).status_code == 204
    with Session(engine) as db:
        assert db.query(PushToken).one().user_id == MEMBER
    identity['id'] = MEMBER
    assert client.post(PATH+'/remove', json={'token': TOKEN}).status_code == 204
    with Session(engine) as db:
        assert db.query(PushToken).count() == 0

@pytest.mark.parametrize('payload', [{'token': 'invalid', 'platform': 'ios'},
    {'token': TOKEN, 'platform': 'web'}, {'token': TOKEN, 'platform': 'ios', 'user_id': MEMBER}])
def test_registration_validation(push_api, payload):
    assert push_api[0].put(PATH, json=payload).status_code == 422
