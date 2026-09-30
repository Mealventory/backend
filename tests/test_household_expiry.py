from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
from sqlalchemy import text
from tests.test_household_inventory import inventory_api, HOME, OTHER, OWNER, MEMBER
from app.services import household_expiry_service as service

@pytest.fixture
def predictor(monkeypatch):
    client=AsyncMock()
    client.post.return_value=httpx.Response(200,json={'predicted_expiry_date':str(date.today()+timedelta(days=6))},request=httpx.Request('POST','http://ai/scan/predict-expiry'))
    context=MagicMock()
    context.__aenter__=AsyncMock(return_value=client)
    context.__aexit__=AsyncMock(return_value=False)
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:context)
    return client

def payload(**kwargs):
    return dict(name='Uncatalogued food', storage_zone='fridge', purchase_date=str(date.today()), avg_shelf_life_days=7, **kwargs)

def test_prediction_preserves_date_until_explicit_save(inventory_api,predictor):
    client,identity,_=inventory_api
    headers={'X-Household-ID':HOME}
    saved=client.post('/api/v1/items',headers=headers,json={'name':'Milk','expiry_date':'2030-01-01'}).json()
    identity['id']=MEMBER
    result=client.post('/api/v1/items/predict-expiry',headers=headers,json=payload(item_id=saved['id']))
    assert result.status_code==200,result.text
    assert result.json()['source']=='model'
    params=predictor.post.call_args.kwargs['params']
    assert params['temperature']==4 and params['humidity']==50 and params['avg_shelf_life_days']==7
    assert params['purchase_date']==str(date.today())
    assert predictor.post.call_args.args[0].endswith('/scan/predict-expiry')
    assert client.get('/api/v1/items',headers=headers).json()[0]['expiry_date']=='2030-01-01'
    prediction=result.json()['predicted_expiry_date']
    assert client.patch('/api/v1/items/'+saved['id'],headers=headers,json={'expiry_date':prediction}).status_code==200
    assert client.get('/api/v1/items',headers=headers).json()[0]['expiry_date']==prediction

def test_unauthorized_household_never_calls_model(inventory_api,predictor):
    client,_,_=inventory_api
    assert client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':OTHER},json=payload()).status_code==403
    predictor.post.assert_not_awaited()

def test_unknown_item_never_calls_model(inventory_api,predictor):
    client,_,_=inventory_api
    result=client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':HOME},json=payload(item_id='99999999-0000-0000-0000-000000000001'))
    assert result.status_code==404
    predictor.post.assert_not_awaited()

@pytest.mark.parametrize('zone',['freezer','spicerack'])
def test_unsupported_zone_returns_no_estimate(inventory_api,predictor,zone):
    client,_,_=inventory_api
    body=payload();body['storage_zone']=zone
    result=client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':HOME},json=body)
    assert result.json()['predicted_expiry_date'] is None
    predictor.post.assert_not_awaited()

def test_unknown_baseline_is_not_fabricated(inventory_api,predictor):
    client,_,_=inventory_api
    body=payload();body.pop('avg_shelf_life_days')
    result=client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':HOME},json=body)
    assert result.json()['source']=='unavailable'
    predictor.post.assert_not_awaited()

@pytest.mark.parametrize('broken',[None,'not-a-date','2099-01-01'])
def test_bad_model_outputs_do_not_produce_dates(inventory_api,predictor,broken):
    client,_,_=inventory_api
    predictor.post.return_value=httpx.Response(200,json={'predicted_expiry_date':broken},request=httpx.Request('POST','http://ai'))
    result=client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':HOME},json=payload())
    assert result.json()['source']=='unavailable'
    assert result.json()['predicted_expiry_date'] is None

def test_timeout_allows_manual_fallback(inventory_api,predictor):
    client,_,_=inventory_api
    predictor.post.side_effect=httpx.ReadTimeout('offline')
    assert client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':HOME},json=payload()).json()['source']=='unavailable'

@pytest.mark.parametrize('change',[{'purchase_date':'2999-01-01'},{'avg_shelf_life_days':0},{'avg_shelf_life_days':31},{'name':''}])
def test_invalid_inputs_rejected(inventory_api,predictor,change):
    client,_,_=inventory_api
    assert client.post('/api/v1/items/predict-expiry',headers={'X-Household-ID':HOME},json={**payload(),**change}).status_code==422
    predictor.post.assert_not_awaited()


def catalogue_payload(name='Yogurt', **kwargs):
    return dict(name=name, storage_zone='fridge', purchase_date=str(date.today()), **kwargs)


def test_catalogue_needs_condition_and_uses_opening_date(inventory_api, predictor):
    client, _, _ = inventory_api
    headers = {'X-Household-ID': HOME}
    body = catalogue_payload()
    first = client.post('/api/v1/items/predict-expiry', headers=headers, json=body).json()
    assert first['predicted_expiry_date'] is None
    assert first['food_state_options'] == ['opened', 'unopened']
    opened = date.today() - timedelta(days=2)
    body.update(food_state='opened', purchase_date=str(opened))
    result = client.post('/api/v1/items/predict-expiry', headers=headers, json=body).json()
    assert result['source'] == 'catalogue'
    assert result['predicted_expiry_date'] == str(opened + timedelta(days=3))
    assert result['source_url'].startswith('https://www.canada.ca/')
    assert result['shelf_life_days'] == 3
    predictor.post.assert_not_awaited()


@pytest.mark.parametrize('name,state,days', [
    ('  GREEK YOGHURT  ', 'opened', 3), ('Carrots', 'whole', 14),
    ('blueberries', 'whole', 2), ('clementines', 'whole', 14),
    ('chicken breast', 'raw', 2), ('chicken breast', 'cooked', 3),
    ('ground beef', 'raw', 1), ('eggs', 'raw', 21), ('ginger root', 'whole', 14),
])
def test_curated_aliases_and_conditions(inventory_api, predictor, name, state, days):
    client, _, _ = inventory_api
    result = client.post('/api/v1/items/predict-expiry', headers={'X-Household-ID': HOME},
                        json=catalogue_payload(name, food_state=state)).json()
    assert result['source'] == 'catalogue'
    assert result['predicted_expiry_date'] == str(date.today() + timedelta(days=days))
    predictor.post.assert_not_awaited()


@pytest.mark.parametrize('body', [
    catalogue_payload('milk', food_state='unopened'),
    {**catalogue_payload('yogurt', food_state='opened'), 'storage_zone': 'pantry'},
    {**catalogue_payload('yogurt', food_state='opened'), 'storage_zone': 'freezer'},
    catalogue_payload('chicken', food_state='whole'),
    catalogue_payload('cooked chicken soup'), catalogue_payload('almond milk'),
    catalogue_payload('frozen carrots'), catalogue_payload('strawberry jam'),
])
def test_no_guess_for_wrong_condition_zone_or_composite_food(inventory_api, predictor, body):
    client, _, _ = inventory_api
    result = client.post('/api/v1/items/predict-expiry', headers={'X-Household-ID': HOME}, json=body).json()
    assert result['source'] == 'unavailable'
    assert result['predicted_expiry_date'] is None
    predictor.post.assert_not_awaited()


def test_catalogue_preserves_inventory_and_rejects_other_household(inventory_api, predictor):
    client, identity, _ = inventory_api
    headers = {'X-Household-ID': HOME}
    row = client.post('/api/v1/items', headers=headers, json={'name': 'Carrots', 'expiry_date': '2030-01-01'}).json()
    identity['id'] = MEMBER
    body = catalogue_payload('carrots', food_state='whole', item_id=row['id'])
    response = client.post('/api/v1/items/predict-expiry', headers=headers, json=body)
    assert response.status_code == 200 and response.json()['source'] == 'catalogue'
    assert client.get('/api/v1/items', headers=headers).json()[0]['expiry_date'] == '2030-01-01'
    assert client.post('/api/v1/items/predict-expiry', headers={'X-Household-ID': OTHER}, json=body).status_code == 403
    predictor.post.assert_not_awaited()


def test_pantry_bread_and_past_estimate_are_not_shifted_to_today(inventory_api, predictor):
    client, _, _ = inventory_api
    start = date.today() - timedelta(days=10)
    body = dict(name='bread', storage_zone='pantry', food_state='ready_to_eat', purchase_date=str(start))
    result = client.post('/api/v1/items/predict-expiry', headers={'X-Household-ID': HOME}, json=body).json()
    assert result['predicted_expiry_date'] == str(start + timedelta(days=3))
    predictor.post.assert_not_awaited()


def test_catalogue_data_has_unique_keys_and_sources():
    from app.services.shelf_life_catalogue import catalogue
    keys = set()
    for entry in catalogue():
        assert entry['source_url'].startswith('https://')
        assert entry['days'] is None or 0 < entry['days'] <= 30
        for alias in entry['aliases']:
            key = (alias, entry['zone'], entry['state'])
            assert key not in keys
            keys.add(key)


def test_ginger_pantry_uses_its_own_guidance(inventory_api, predictor):
    client, _, _ = inventory_api
    body = {**catalogue_payload('ginger', food_state='whole'), 'storage_zone': 'pantry'}
    result = client.post('/api/v1/items/predict-expiry', headers={'X-Household-ID': HOME}, json=body).json()
    assert result['shelf_life_days'] == 7
    assert result['source_name'] == 'Iowa State University Extension'
    predictor.post.assert_not_awaited()
