"""Tests for shopping trip item claims, handoffs, trip ending, and household isolation (#127)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.main import app
from app.models.household import Household
from app.models.shopping import ShoppingListItem
from app.services import shopping_service
from tests.test_household_inventory import (
    HOME,
    MEMBER,
    OTHER,
    OUTSIDER,
    OWNER,
    inventory_api,
)

PATH = '/api/v1/shopping'
HEADERS = {'X-Household-ID': HOME}


@pytest.fixture
def claims_api(inventory_api):
    client, identity, engine = inventory_api
    Household.__table__.create(engine)
    ShoppingListItem.__table__.create(engine)
    with Session(engine) as db:
        db.add(Household(id=HOME, name='Home', created_by=OWNER, invite_code='HOME01'))
        db.add(Household(id=OTHER, name='Other', created_by=OUTSIDER, invite_code='OTHR01'))
        db.commit()
    return client, identity, engine


def test_claim_conflict_release_and_purchased_independence(claims_api):
    client, identity, _ = claims_api
    item = client.post(PATH, headers=HEADERS, json={'name': 'Milk'}).json()
    assert item['claimed_by'] is None
    assert item['checked'] is False

    # Owner claims item; claim is idempotent and does not mark checked
    identity['id'] = OWNER
    claimed = client.post(f"{PATH}/{item['id']}/claim", headers=HEADERS)
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert body['claimed_by'] == OWNER
    assert body['claimed_at'] is not None
    assert body['claim_expires_at'] is not None
    assert body['checked'] is False

    repeat = client.post(f"{PATH}/{item['id']}/claim", headers=HEADERS, json={'ttl_minutes': 60})
    assert repeat.status_code == 200
    assert repeat.json()['claimed_by'] == OWNER

    # Another member sees the claim and gets 409 conflict without exposing unrelated user info
    identity['id'] = MEMBER
    listed = client.get(PATH, headers=HEADERS).json()
    assert listed[0]['claimed_by'] == OWNER

    conflict = client.post(f"{PATH}/{item['id']}/claim", headers=HEADERS)
    assert conflict.status_code == 409
    problem = conflict.json()
    assert problem['code'] == 'shopping_item_already_claimed'
    assert 'email' not in problem

    # Non-owner cannot release another member's active claim
    blocked_release = client.delete(f"{PATH}/{item['id']}/claim", headers=HEADERS)
    assert blocked_release.status_code == 409
    assert blocked_release.json()['code'] == 'shopping_item_claimed_by_other'

    # Purchasing checkbox stays independent of claim
    checked = client.patch(f"{PATH}/{item['id']}", headers=HEADERS, json={'checked': True})
    assert checked.status_code == 200
    assert checked.json()['checked'] is True
    assert checked.json()['claimed_by'] == OWNER

    # Owner releases claim idempotently
    identity['id'] = OWNER
    released = client.delete(f"{PATH}/{item['id']}/claim", headers=HEADERS)
    assert released.status_code == 200
    assert released.json()['claimed_by'] is None
    assert released.json()['checked'] is True

    released_again = client.delete(f"{PATH}/{item['id']}/claim", headers=HEADERS)
    assert released_again.status_code == 200
    assert released_again.json()['claimed_by'] is None


def test_handoff_end_trip_and_expired_claim_recovery(claims_api):
    client, identity, engine = claims_api
    milk = client.post(PATH, headers=HEADERS, json={'name': 'Milk'}).json()
    eggs = client.post(PATH, headers=HEADERS, json={'name': 'Eggs'}).json()

    identity['id'] = MEMBER
    assert client.post(f"{PATH}/{milk['id']}/claim", headers=HEADERS).status_code == 200

    # Handoff from member to owner
    handed = client.post(
        f"{PATH}/{milk['id']}/handoff",
        headers=HEADERS,
        json={'target_user_id': OWNER},
    )
    assert handed.status_code == 200, handed.text
    assert handed.json()['claimed_by'] == OWNER

    # Handoff to outsider fails with 404
    assert (
        client.post(
            f"{PATH}/{eggs['id']}/handoff",
            headers=HEADERS,
            json={'target_user_id': OUTSIDER},
        ).status_code
        == 404
    )

    # Member cannot hand off an item actively claimed by owner
    assert (
        client.post(
            f"{PATH}/{milk['id']}/handoff",
            headers=HEADERS,
            json={'target_user_id': MEMBER},
        ).status_code
        == 409
    )

    # Member claims eggs, then ends own trip (only member's claim clears)
    assert client.post(f"{PATH}/{eggs['id']}/claim", headers=HEADERS).status_code == 200
    ended = client.post(f"{PATH}/trip/end", headers=HEADERS, json={'scope': 'mine'})
    assert ended.status_code == 200
    assert ended.json() == {'released_count': 1}
    assert client.post(f"{PATH}/trip/end", headers=HEADERS).json() == {'released_count': 0}

    items = {row['id']: row for row in client.get(PATH, headers=HEADERS).json()}
    assert items[eggs['id']]['claimed_by'] is None
    assert items[milk['id']]['claimed_by'] == OWNER

    # End all trip claims
    ended_all = client.post(f"{PATH}/trip/end", headers=HEADERS, json={'scope': 'all'})
    assert ended_all.status_code == 200
    assert ended_all.json() == {'released_count': 1}

    # Expired claim is hidden in list and can be claimed by another shopper
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    with engine.begin() as db:
        db.execute(
            text(
                'UPDATE shopping_list_items '
                'SET claimed_by=:owner, claimed_at=:past, claim_expires_at=:past '
                'WHERE id=:id'
            ),
            {'owner': OWNER, 'past': past, 'id': milk['id']},
        )
    assert client.get(PATH, headers=HEADERS).json()[0]['claimed_by'] is None
    reclaimed = client.post(f"{PATH}/{milk['id']}/claim", headers=HEADERS)
    assert reclaimed.status_code == 200
    assert reclaimed.json()['claimed_by'] == MEMBER


def test_departing_member_clears_claims_and_isolation(claims_api):
    client, identity, _ = claims_api
    item = client.post(PATH, headers=HEADERS, json={'name': 'Apples'}).json()

    identity['id'] = MEMBER
    assert client.post(f"{PATH}/{item['id']}/claim", headers=HEADERS).status_code == 200

    # Member leaves household -> claim is cleared
    assert client.delete(f"/api/v1/households/{HOME}/members/{MEMBER}").status_code == 204

    identity['id'] = OWNER
    items = client.get(PATH, headers=HEADERS).json()
    assert items[0]['claimed_by'] is None

    # Household isolation & auth checks for every new route
    identity['id'] = OUTSIDER
    other_headers = {'X-Household-ID': OTHER}
    for method, url, payload in [
        ('post', f"{PATH}/trip/end", {'scope': 'mine'}),
        ('post', f"{PATH}/{item['id']}/claim", None),
        ('delete', f"{PATH}/{item['id']}/claim", None),
        ('post', f"{PATH}/{item['id']}/handoff", {'target_user_id': OUTSIDER}),
    ]:
        assert client.request(method, url, headers=HEADERS, json=payload).status_code == 403
        if '/trip/end' not in url:
            assert client.request(method, url, headers=other_headers, json=payload).status_code == 404

    assert client.post(f"{PATH}/trip/end").status_code == 400
    app.dependency_overrides.pop(get_current_user)
    for method, url, payload in [
        ('post', f"{PATH}/trip/end", None),
        ('post', f"{PATH}/{item['id']}/claim", None),
        ('delete', f"{PATH}/{item['id']}/claim", None),
        ('post', f"{PATH}/{item['id']}/handoff", {'target_user_id': OWNER}),
    ]:
        assert client.request(method, url, headers=HEADERS, json=payload).status_code == 401
