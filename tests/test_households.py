import re
from unittest.mock import patch
import pytest
from sqlalchemy import event
from app.models.household import Household
from app.models.household_member import HouseholdMember
from tests.test_supabase_auth import secured_client, headers, token, claims, UID, OTHER

THIRD = '10000000-0000-0000-0000-000000000003'


def create(client, name='Smith Family'):
    response = client.post('/api/v1/households', headers=headers(), json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()


def join(client, code, user=OTHER):
    return client.post('/api/v1/households/join', headers=headers(token(claims(sub=user))),
                       json={'invite_code': code})


def test_create_owner_and_list(secured_client, db):
    household = create(secured_client, '  Smith Family  ')
    assert household['name'] == 'Smith Family'
    assert re.fullmatch('[A-Z0-9]{6}', household['invite_code'])
    assert household['role'] == 'owner'
    assert db.get(Household, household['id']).created_by == UID
    assert db.get(HouseholdMember, (household['id'], UID)).role == 'owner'
    assert secured_client.get('/api/v1/households/me', headers=headers()).json() == [household]
    assert secured_client.get('/api/v1/households/me', headers=headers(token(claims(sub=OTHER)))).json() == []


def test_join_normalizes_code_and_is_idempotent(secured_client, db):
    hh = create(secured_client)
    for _ in range(2):
        response = join(secured_client, ' ' + hh['invite_code'].lower() + ' ')
        assert response.status_code == 200
        assert response.json()['role'] == 'member'
    assert join(secured_client, hh['invite_code'], UID).json()['role'] == 'owner'
    assert db.query(HouseholdMember).filter_by(household_id=hh['id']).count() == 2
    assert len(secured_client.get('/api/v1/households/me', headers=headers(token(claims(sub=OTHER)))).json()) == 1


@pytest.mark.parametrize('payload', [{'name':''}, {'name':'   '}, {'name':'x'*121}, {'name':'Home','created_by':OTHER}, {'name':'Home','role':'owner'}])
def test_invalid_creation_payload(secured_client, payload):
    assert secured_client.post('/api/v1/households', headers=headers(), json=payload).status_code == 422


@pytest.mark.parametrize('code', ['', 'ABCDE', 'ABCDEFG', 'AB!DEF'])
def test_invalid_code_format(secured_client, code):
    assert join(secured_client, code).status_code == 422


def test_unknown_code(secured_client):
    assert join(secured_client, 'ZZZZZZ').status_code == 404


def test_permissions_and_last_owner(secured_client, db):
    hh = create(secured_client); hid=hh['id']
    join(secured_client, hh['invite_code'])
    member_url=f'/api/v1/households/{hid}/members'
    other_headers=headers(token(claims(sub=OTHER)))
    outsider=headers(token(claims(sub=THIRD)))
    assert len(secured_client.get(member_url,headers=other_headers).json()) == 2
    assert secured_client.get(member_url,headers=outsider).status_code == 403
    assert secured_client.patch(member_url+'/'+OTHER,headers=outsider,json={'role':'owner'}).status_code == 403
    assert secured_client.patch(member_url+'/'+OTHER,headers=other_headers,json={'role':'owner'}).status_code == 403
    assert secured_client.delete(member_url+'/'+UID,headers=other_headers).status_code == 403
    assert secured_client.delete(member_url+'/'+UID,headers=headers()).status_code == 409
    assert secured_client.patch(member_url+'/'+UID,headers=headers(),json={'role':'member'}).status_code == 409
    assert secured_client.patch(member_url+'/'+OTHER,headers=headers(),json={'role':'admin'}).json()['role'] == 'admin'
    assert secured_client.patch(member_url+'/'+UID,headers=other_headers,json={'role':'member'}).status_code == 403
    join(secured_client,hh['invite_code'],THIRD)
    assert secured_client.delete(member_url+'/'+THIRD,headers=other_headers).status_code == 204
    assert db.get(HouseholdMember,(hid,THIRD)) is None
    assert secured_client.patch(member_url+'/'+OTHER,headers=headers(),json={'role':'owner'}).status_code == 200
    assert secured_client.delete(member_url+'/'+UID,headers=headers()).status_code == 204
    assert secured_client.get(member_url,headers=headers()).status_code == 403
    assert secured_client.delete(member_url+'/'+OTHER,headers=other_headers).status_code == 409


def test_member_can_leave_and_unknown_target(secured_client):
    hh=create(secured_client);join(secured_client,hh['invite_code'])
    url=f"/api/v1/households/{hh['id']}/members/"
    assert secured_client.delete(url+THIRD,headers=headers()).status_code == 404
    assert secured_client.patch(url+THIRD,headers=headers(),json={'role':'member'}).status_code == 404
    assert secured_client.delete(url+OTHER,headers=headers(token(claims(sub=OTHER)))).status_code == 204


def test_code_collision_retries_and_exhaustion(secured_client, db):
    with patch('app.services.household_service.generate_invite_code',return_value='ABC123'):
        first=create(secured_client)
    with patch('app.services.household_service.generate_invite_code',side_effect=['ABC123','DEF456']):
        second=create(secured_client)
    assert first['id'] != second['id']
    assert second['invite_code'] == 'DEF456'
    with patch('app.services.household_service.generate_invite_code',return_value='ABC123'):
        assert secured_client.post('/api/v1/households',headers=headers(),json={'name':'Fail'}).status_code == 503
    assert db.query(Household).count() == 2


def test_owner_insert_failure_rolls_back_household(secured_client, db):
    def fail(*args):
        raise RuntimeError('simulated owner insert failure')
    event.listen(HouseholdMember,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):
            create(secured_client)
    finally:
        event.remove(HouseholdMember,'before_insert',fail)
    assert db.query(Household).count() == 0


@pytest.mark.parametrize('method,path,payload',[
 ('post','/api/v1/households',{'name':'Home'}),
 ('post','/api/v1/households/join',{'invite_code':'ABC123'}),
 ('get','/api/v1/households/me',None),
 ('get',f'/api/v1/households/{UID}/members',None),
 ('patch',f'/api/v1/households/{UID}/members/{OTHER}',{'role':'owner'}),
 ('delete',f'/api/v1/households/{UID}/members/{OTHER}',None),
])
def test_household_routes_require_auth(secured_client,method,path,payload):
    response=secured_client.request(method,path,json=payload)
    assert response.status_code == 401
    assert response.headers['content-type'] == 'application/problem+json'
