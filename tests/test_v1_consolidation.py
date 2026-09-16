import ast
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.main import app
from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.models.inventory import InventoryItem
from app.models.user import User


def test_both_launch_modules_use_same_application():
    from main import app as launcher
    assert launcher is app


@pytest.mark.parametrize('path', ['/api/v0/items', '/api/v0/items/1', '/inventory/',
                                  '/food-items/', '/scan/', '/scan/scan/normalize',
                                  '/recipes/', '/recipes/generate', '/health/', '/test'])
@pytest.mark.parametrize('method', ['get', 'post'])
def test_retired_endpoints_are_not_registered(client, path, method):
    assert getattr(client, method)(path).status_code == 404


def test_openapi_preserves_v1_contract(client):
    baseline = json.loads((Path(__file__).parent/'contracts/v1-openapi.json').read_text())
    current = client.get('/openapi.json').json()
    assert current['components'] == baseline['components']
    assert current['paths'].keys() == baseline['paths'].keys()
    for path, methods in baseline['paths'].items():
        for verb, operation in methods.items():
            actual = current['paths'][path][verb]
            # Human-readable descriptions may improve; IDs, validation and responses may not drift.
            assert {k:v for k,v in actual.items() if k!='description'} == {k:v for k,v in operation.items() if k!='description'}
    assert client.get('/docs').status_code == 200
    assert client.get('/').json() == {'status': 'API running'}


def test_user_registration_and_profile(client, db, monkeypatch):
    monkeypatch.setattr('app.services.auth_service.verify_firebase_token', lambda token: {'uid':'new', 'email':'new@example.com'})
    response=client.post('/api/v1/users/register', headers={'Authorization':'Bearer test'})
    assert response.status_code == 201
    assert response.json() == {'id':'new','email':'new@example.com'}
    assert db.get(User,'new') is not None
    assert client.post('/api/v1/users/register', headers={'Authorization':'Bearer test'}).status_code == 201
    assert client.get('/api/v1/users/me').json()['id'] == 'alice'


def test_authentication_and_unregistered_user(client, monkeypatch):
    app.dependency_overrides.pop(get_current_user)
    assert client.get('/api/v1/users/me').status_code in (401,403)
    monkeypatch.setattr('app.services.auth_service.verify_firebase_token', lambda token: {'uid':'missing'})
    assert client.get('/api/v1/users/me',headers={'Authorization':'Bearer test'}).status_code == 404


def test_inventory_crud_and_user_isolation(client, db):
    other=InventoryItem(user_id='bob', food_id=1)
    db.add(other); db.commit()
    response=client.post('/api/v1/inventory/',json={'food_id':1})
    assert response.status_code == 201
    item=response.json()
    assert item['user_id']=='alice' and item['expiry_date']
    assert [i['id'] for i in client.get('/api/v1/inventory/').json()] == [item['id']]
    assert client.delete(f'/api/v1/inventory/{other.id}').status_code == 404
    assert client.delete(f"/api/v1/inventory/{item['id']}").status_code == 204
    assert client.post('/api/v1/inventory/',json={'food_id':999}).status_code == 404


def test_upload_scan_stores_duplicate_items(client,db,monkeypatch):
    monkeypatch.setattr('app.services.scan_service.detect_food',AsyncMock(return_value={'type':'food','items':['chicken','chicken']}))
    response=client.post('/api/v1/scan/',data={'mode':'food'},files={'file':('food.jpg',b'image','image/jpeg')})
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
    assert db.query(InventoryItem).filter_by(user_id='alice').count() == 2


@pytest.mark.parametrize('detection', [{'type':'mismatch','items':[]}, {'type':'food','items':[]}])
def test_upload_scan_rejects_unusable_results(client,monkeypatch,detection):
    monkeypatch.setattr('app.services.scan_service.detect_food',AsyncMock(return_value=detection))
    assert client.post('/api/v1/scan/',data={'mode':'food'},files={'file':('x.jpg',b'image','image/jpeg')}).status_code == 422


def test_sample_scan_preview_disabled_and_path_guards(client,db,monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'SAMPLE_IMAGES_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'ENABLE_SAMPLE_SCAN',False)
    payload={'sample_name':'receipt.jpeg','mode':'receipt','persist_to_db':False}
    assert client.post('/api/v1/scan/sample',json=payload).status_code == 403
    monkeypatch.setattr(settings,'ENABLE_SAMPLE_SCAN',True)
    (tmp_path/'receipt.jpeg').write_bytes(b'image')
    monkeypatch.setattr('app.services.scan_service.detect_food',AsyncMock(return_value={'type':'receipt','items':['chicken'],'expiry_dates':[]}))
    response=client.post('/api/v1/scan/sample',json=payload)
    assert response.status_code == 200
    assert response.json()['detected_item_counts'] == {'chicken':1}
    assert response.json()['stored_count'] == 0
    assert db.query(InventoryItem).count() == 0
    for name,status in [('../outside.jpeg',400),('image.png',400),('missing.jpeg',404)]:
        assert client.post('/api/v1/scan/sample',json={**payload,'sample_name':name}).status_code == status


def test_recipes_with_inventory(client,db,monkeypatch):
    assert client.get('/api/v1/recipes/').status_code == 404
    db.add(InventoryItem(user_id='alice',food_id=1)); db.commit()
    generator=AsyncMock(return_value={'recipes':[{'title':'Chicken dinner'}]})
    monkeypatch.setattr('app.services.recipe_service.get_recipes_for_inventory',generator)
    response=client.get('/api/v1/recipes/')
    assert response.status_code == 200
    assert response.json()['recipes'][0]['title']=='Chicken dinner'
    generator.assert_awaited_once_with(['chicken'])


def test_food_prediction_contract(client):
    params={'purchase_date':'2026-09-15','temperature':20,'humidity':50}
    response=client.post('/api/v1/food/predict-expiry/1',params=params)
    assert response.status_code==200
    assert response.json()['predicted_expiry_date']=='2026-09-22'
    assert client.post('/api/v1/food/predict-expiry/999',params=params).status_code==404


def test_no_imports_of_retired_modules():
    root=Path(__file__).resolve().parents[1]
    for path in (root/'app').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            modules=[]
            if isinstance(node,ast.Import): modules=[n.name for n in node.names]
            elif isinstance(node,ast.ImportFrom) and node.level==0: modules=[node.module or '']
            assert not any(m.split('.')[0] in {'api','core','services','schemas','utils'} for m in modules),path
