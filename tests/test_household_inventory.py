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
    with engine.begin() as c:
        c.execute(text('''CREATE TABLE foods (id text PRIMARY KEY, name text NOT NULL,
            category text, default_unit text NOT NULL)'''))
        c.execute(text('''CREATE TABLE inventory_items (id text PRIMARY KEY,
            household_id text NOT NULL, food_id text NOT NULL, quantity numeric NOT NULL,
            unit text NOT NULL, expiry_date date, status text NOT NULL,
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
