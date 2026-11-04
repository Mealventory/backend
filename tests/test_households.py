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


def rotate(client, household_id, user=UID):
    return client.post(
        f'/api/v1/households/{household_id}/invite-code/rotate',
        headers=headers(token(claims(sub=user))),
    )


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


@pytest.mark.parametrize(
    ('email', 'metadata', 'expected_name', 'expected_username'),
    [
        ('JohnnyTest@gmail.com', {}, 'JohnnyTest', None),
        ('JohnnyTest@gmail.com', {'username': 'ChefJohnny'}, 'ChefJohnny', 'ChefJohnny'),
        ('JohnnyTest@gmail.com', {'display_name': 'Johnny T.'}, 'Johnny T.', None),
        ('JohnnyTest@gmail.com', {'username': '  ', 'display_name': '  '}, 'JohnnyTest', None),
        (' JohnnyTest@gmail.com ', {'username': '  ChefJohnny  '}, 'ChefJohnny', 'ChefJohnny'),
        (None, {}, None, None),
    ],
)
def test_member_identity_uses_explicit_name_or_preserves_email_prefix(
    email, metadata, expected_name, expected_username
):
    from app.services.household_service import _member_identity
    assert _member_identity(email, metadata) == (expected_name, expected_username)


def test_member_profiles_are_loaded_from_supabase_auth_without_exposing_emails():
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    from app.services.household_service import _auth_member_profiles

    db = MagicMock()
    db.get_bind.return_value.dialect.name = 'postgresql'
    db.execute.side_effect = [
        SimpleNamespace(scalar=lambda: 'auth.users'),
        SimpleNamespace(scalar=lambda: True),
        SimpleNamespace(mappings=lambda: [
            {
                'user_id': UID,
                'email': 'Owner@example.com',
                'raw_user_meta_data': {'username': 'OwnerName'},
            },
            {
                'user_id': OTHER,
                'email': 'JohnnyTest@gmail.com',
                'raw_user_meta_data': {},
            },
        ]),
    ]
    profiles = _auth_member_profiles(db, [UID, OTHER])
    assert profiles == {
        UID: {'display_name': 'OwnerName', 'username': 'OwnerName'},
        OTHER: {'display_name': 'JohnnyTest', 'username': None},
    }
    auth_query = db.execute.call_args_list[2]
    assert 'FROM auth.users' in str(auth_query.args[0])
    assert auth_query.args[1]['user_ids'] == [UID, OTHER]
    assert all('email' not in profile for profile in profiles.values())


def test_member_profile_lookup_skips_databases_without_supabase_auth():
    from unittest.mock import MagicMock
    from app.services.household_service import _auth_member_profiles

    db = MagicMock()
    db.get_bind.return_value.dialect.name = 'sqlite'
    assert _auth_member_profiles(db, [UID]) == {}
    db.execute.assert_not_called()


def test_household_members_show_resolved_names_only_to_fellow_members(
    secured_client, monkeypatch
):
    from app.services import household_service
    hh = create(secured_client)
    assert join(secured_client, hh['invite_code']).status_code == 200
    names = {
        UID: _profile('OwnerName', 'OwnerName'),
        OTHER: _profile('JohnnyTest', None),
    }

    def profiles(_db, user_ids):
        assert set(user_ids) == {UID, OTHER}
        return names

    monkeypatch.setattr(household_service, '_auth_member_profiles', profiles)
    url = f"/api/v1/households/{hh['id']}/members"
    rows = secured_client.get(url, headers=headers()).json()
    assert {row['user_id']: row['display_name'] for row in rows} == {
        UID: 'OwnerName', OTHER: 'JohnnyTest'
    }
    assert {row['user_id']: row['username'] for row in rows} == {
        UID: 'OwnerName', OTHER: None
    }
    assert all('email' not in row for row in rows)
    assert secured_client.get(
        url, headers=headers(token(claims(sub=THIRD)))
    ).status_code == 403


def _profile(display_name, username):
    return {'display_name': display_name, 'username': username}


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



def test_owner_rotates_code_revokes_old_and_preserves_members(secured_client, db):
    hh = create(secured_client)
    old_code = hh['invite_code']
    assert join(secured_client, old_code).status_code == 200

    with patch('app.services.household_service.generate_invite_code', return_value='NEW123'):
        response = rotate(secured_client, hh['id'])

    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated['invite_code'] == 'NEW123'
    assert rotated['role'] == 'owner'
    assert rotated['id'] == hh['id']

    assert db.get(HouseholdMember, (hh['id'], UID)).role == 'owner'
    assert db.get(HouseholdMember, (hh['id'], OTHER)).role == 'member'
    assert join(secured_client, old_code, THIRD).status_code == 404
    assert join(secured_client, 'NEW123', THIRD).status_code == 200
    assert db.get(HouseholdMember, (hh['id'], THIRD)).role == 'member'


def test_non_owner_cannot_rotate_invite_code(secured_client, db):
    hh = create(secured_client)
    old_code = hh['invite_code']
    assert join(secured_client, old_code).status_code == 200

    response = rotate(secured_client, hh['id'], OTHER)

    assert response.status_code == 403
    assert db.get(Household, hh['id']).invite_code == old_code


def test_rotation_retries_collisions_and_preserves_code_on_exhaustion(secured_client, db):
    with patch('app.services.household_service.generate_invite_code', return_value='AAA111'):
        first = create(secured_client, 'First')
    with patch('app.services.household_service.generate_invite_code', return_value='BBB222'):
        second = create(secured_client, 'Second')

    with patch(
        'app.services.household_service.generate_invite_code',
        side_effect=['BBB222', 'CCC333'],
    ):
        response = rotate(secured_client, first['id'])
    assert response.status_code == 200
    assert response.json()['invite_code'] == 'CCC333'

    with patch('app.services.household_service.generate_invite_code', return_value='BBB222'):
        response = rotate(secured_client, first['id'])
    assert response.status_code == 503
    assert db.get(Household, first['id']).invite_code == 'CCC333'
    assert db.get(Household, second['id']).invite_code == 'BBB222'


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
 ('post',f'/api/v1/households/{UID}/invite-code/rotate',None),
 ('get',f'/api/v1/households/{UID}/members',None),
 ('patch',f'/api/v1/households/{UID}/members/{OTHER}',{'role':'owner'}),
 ('delete',f'/api/v1/households/{UID}/members/{OTHER}',None),
])
def test_household_routes_require_auth(secured_client,method,path,payload):
    response=secured_client.request(method,path,json=payload)
    assert response.status_code == 401
    assert response.headers['content-type'] == 'application/problem+json'
